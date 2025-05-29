import os
import sys
import zipfile
import shutil
from PIL import Image, ImageFile
import re
import datetime
import collections
import uuid

ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- Helper Functions (adapted from jpg2epub.py) ---

def create_directory(path):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
            print(f"Directory created: {path}")
        except Exception as error:
            print(f"Error: Unable to create directory {path}. Reason: {error}")
            # Depending on context, might raise error or return False
            raise 

def create_file(path, content):
    try:
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)
    except Exception as error:
        print(f"Error: Unable to create file {path}. Reason: {error}")
        raise

def extract_number(folder_name):
    match = re.search(r'(\d+(\.\d+)?)', folder_name)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return float('inf')
    return float('inf')

def find_and_sort_subfolders(parent_folder):
    subfolders = []
    try:
        for item in os.listdir(parent_folder):
            item_path = os.path.join(parent_folder, item)
            if os.path.isdir(item_path) and re.search(r'\d', item):
                 subfolders.append(item)
    except FileNotFoundError:
        print(f"Error: Parent folder {parent_folder} not found.")
        return [] # Return empty list on error
    except Exception as e:
        print(f"Error reading folder {parent_folder}: {e}")
        return []

    subfolders.sort(key=extract_number)
    print(f"Found and sorted subfolders: {subfolders}")
    return subfolders

def collect_all_images_from_subfolders(parent_folder, sorted_subfolders):
    all_images = []
    image_pattern = re.compile(r'^(\d{3})\.(jpg|jpeg|png|webp)$', re.IGNORECASE)

    for subfolder in sorted_subfolders:
        subfolder_path = os.path.join(parent_folder, subfolder)
        img_files_in_subfolder = []
        try:
            for file in os.listdir(subfolder_path):
                match = image_pattern.match(file)
                if match:
                    file_path = os.path.join(subfolder_path, file)
                    if os.path.isfile(file_path):
                        img_files_in_subfolder.append(file)
        except FileNotFoundError:
            print(f"Warning: Subfolder {subfolder_path} not found, skipping.")
            continue
        except Exception as e:
            print(f"Warning: Error reading subfolder {subfolder_path}: {e}, skipping.")
            continue
        
        img_files_in_subfolder.sort(key=lambda f: int(image_pattern.match(f).group(1)))
        for img_file in img_files_in_subfolder:
            all_images.append(os.path.join(subfolder_path, img_file))
    return all_images

def collect_direct_images_from_folder(folder_path):
    direct_images = []
    image_pattern = re.compile(r'^(\d{3})\.(jpg|jpeg|png|webp)$', re.IGNORECASE)
    
    try:
        img_files_in_folder = []
        for file in os.listdir(folder_path):
            match = image_pattern.match(file)
            if match:
                file_path = os.path.join(folder_path, file)
                if os.path.isfile(file_path):
                    img_files_in_folder.append(file)

        if not img_files_in_folder:
            print(f"Info: No suitable image files (e.g., 001.jpg) found in {folder_path}.")
            return []

        img_files_in_folder.sort(key=lambda f: int(image_pattern.match(f).group(1)))
        for img_file in img_files_in_folder:
            direct_images.append(os.path.join(folder_path, img_file))
            
    except FileNotFoundError:
        print(f"Error: Folder {folder_path} not found.")
        return []
    except Exception as e:
        print(f"Error reading folder {folder_path}: {e}")
        return []
    return direct_images

def process_and_copy_image(src_path, dst_path, target_width, target_height):
    try:
        with Image.open(src_path) as img:
            img.load()
            if img.mode == 'P':
                 img = img.convert('RGBA')
            elif img.mode != 'RGB' and img.mode != 'RGBA': # Allow RGBA for PNGs
                 img = img.convert('RGB')

            orig_width, orig_height = img.size

            if orig_width == target_width and orig_height == target_height:
                shutil.copy2(src_path, dst_path) # Use shutil.copy2 to preserve metadata if possible
                print(f"  Copied (size matched): {os.path.basename(src_path)}")
                return True

            orig_aspect = orig_width / orig_height
            target_aspect = target_width / target_height
            resample_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS

            print(f"  Processing: {os.path.basename(src_path)} (Original: {orig_width}x{orig_height}, Target: {target_width}x{target_height})")

            if abs(orig_aspect - target_aspect) < 0.01: # Aspect ratios are close enough
                print(f"    Resizing image...")
                resized_img = img.resize((target_width, target_height), resample_filter)
            else: # Aspect ratios differ, crop from top-left and resize
                print(f"    Cropping (from top-left) and resizing image...")
                crop_box = None
                if orig_aspect > target_aspect: # Original is wider
                    crop_width = int(orig_height * target_aspect)
                    crop_box = (0, 0, crop_width, orig_height)
                else: # Original is taller
                    crop_height = int(orig_width / target_aspect)
                    crop_box = (0, 0, orig_width, crop_height)
                
                cropped_img = img.crop(crop_box)
                resized_img = cropped_img.resize((target_width, target_height), resample_filter)
            
            # Ensure the destination directory exists before saving
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            resized_img.save(dst_path)
            return True
    except Exception as e:
        print(f"Warning: Failed to process image {src_path}. Reason: {e}")
        return False

# --- Main EPUB Generation Function ---

def generate_epub_from_folder_content(
    source_folder_path: str,
    output_epub_full_path: str,
    epub_title: str,
    processing_mode: str = 'subfolder', # 'subfolder' or 'direct'
    language_code: str = "zh-CN",
    target_width_override: int = None,
    target_height_override: int = None,
    epub_author: str = "Unknown Author",
    # create_title_page_option: bool = True, # Placeholder - current script focuses on cover
    custom_uuid: str = None
):
    """
    Generates an EPUB file from images in a source folder.
    Uses logic adapted from the original jpg2epub.py script.
    """
    if not os.path.exists(source_folder_path) or not os.path.isdir(source_folder_path):
        print(f"Error: Source folder '{source_folder_path}' not found or is not a directory.")
        return False

    base_folder_name = os.path.basename(source_folder_path)
    # temp_dir is created relative to the output EPUB's directory or source_folder_path if output is relative
    output_dir = os.path.dirname(output_epub_full_path)
    if not output_dir: # If output_epub_full_path is just a filename
        output_dir = os.path.dirname(source_folder_path) # Fallback to source's dir for temp
        
    temp_dir = os.path.join(output_dir, f"temp_epub_build_{base_folder_name}_{uuid.uuid4().hex[:8]}")

    try:
        create_directory(temp_dir)

        all_image_paths = []
        if processing_mode == 'subfolder':
            subfolders = find_and_sort_subfolders(source_folder_path)
            if not subfolders:
                print(f"Error: No suitable subfolders found in '{source_folder_path}' for 'subfolder' mode.")
                return False
            all_image_paths = collect_all_images_from_subfolders(source_folder_path, subfolders)
        elif processing_mode == 'direct':
            all_image_paths = collect_direct_images_from_folder(source_folder_path)
        else:
            print(f"Error: Invalid processing_mode '{processing_mode}'. Must be 'subfolder' or 'direct'.")
            return False

        if not all_image_paths:
            print(f"Error: No images found in '{source_folder_path}' with mode '{processing_mode}'.")
            return False
        
        print(f"Found {len(all_image_paths)} image files. Starting EPUB creation for: {output_epub_full_path}")

        # Create EPUB directory structure
        oebps_dir = os.path.join(temp_dir, "OEBPS")
        images_dir = os.path.join(oebps_dir, "images")
        create_directory(os.path.join(temp_dir, "META-INF"))
        create_directory(oebps_dir)
        create_directory(images_dir)

        create_file(os.path.join(temp_dir, "mimetype"), "application/epub+zip")

        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""
        create_file(os.path.join(temp_dir, "META-INF", "container.xml"), container_xml)

        # Determine target resolution
        actual_target_width = target_width_override
        actual_target_height = target_height_override

        if not actual_target_width or not actual_target_height:
            resolution_counts = collections.Counter()
            valid_image_count_for_res_check = 0
            for img_path in all_image_paths:
                try:
                    with Image.open(img_path) as img:
                        resolution = img.size
                        resolution_counts[resolution] += 1
                        valid_image_count_for_res_check += 1
                except Exception as e:
                    print(f"Warning: Cannot read resolution for {os.path.basename(img_path)}: {e}")
            
            if valid_image_count_for_res_check > 0 and resolution_counts:
                most_common_res, count = resolution_counts.most_common(1)[0]
                if not actual_target_width: actual_target_width = most_common_res[0]
                if not actual_target_height: actual_target_height = most_common_res[1]
                print(f"Auto-detected target resolution: {actual_target_width}x{actual_target_height} (most common, occurred {count} times)")
            else: # Fallback if no images could be read or if overrides are still None
                actual_target_width = actual_target_width or 1200 # Default fallback
                actual_target_height = actual_target_height or 1600 # Default fallback
                print(f"Warning: Could not auto-detect resolution. Using fallback/override: {actual_target_width}x{actual_target_height}")
        
        copied_image_filenames = []
        print("Copying and processing images...")
        for i, img_path in enumerate(all_image_paths):
            _, ext = os.path.splitext(img_path)
            new_img_filename = f"image_{i+1:05d}{ext.lower()}" # Use 5 digits for sorting
            target_img_path_in_epub = os.path.join(images_dir, new_img_filename)
            if process_and_copy_image(img_path, target_img_path_in_epub, actual_target_width, actual_target_height):
                copied_image_filenames.append(new_img_filename)
            else:
                copied_image_filenames.append(None) # Placeholder for failed images

        valid_copied_images = [f for f in copied_image_filenames if f is not None]
        if not valid_copied_images:
            print(f"Error: No images were successfully processed and copied.")
            return False

        # Create XHTML, CSS, OPF, NCX (NAV for EPUB3)
        manifest_items = []
        spine_items = []
        page_list_for_nav = []

        stylesheet_content = """html, body {
    height: 100%; margin: 0; padding: 0; text-align: center; background-color: #fff;
}
img {
    max-width: 100%; max-height: 100vh; object-fit: contain; margin: auto; display: block;
}"""
        create_file(os.path.join(oebps_dir, "stylesheet.css"), stylesheet_content)
        manifest_items.append('<item id="css" href="stylesheet.css" media-type="text/css"/>')

        print("Creating XHTML pages...")
        for idx, img_filename in enumerate(valid_copied_images):
            page_number = idx + 1
            is_cover_image_page = (idx == 0)
            
            # XHTML page ID and filename
            page_id_str = f"page_{page_number:05d}"
            xhtml_filename = "cover.xhtml" if is_cover_image_page else f"{page_id_str}.xhtml"
            html_title = "Cover" if is_cover_image_page else f"Page {page_number}"

            # Image details for manifest
            img_id_str = "cover-image" if is_cover_image_page else f"img_{page_number:05d}"
            img_properties = 'properties="cover-image" ' if is_cover_image_page else ''
            _, img_ext = os.path.splitext(img_filename)
            media_type = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif'
            }.get(img_ext.lower(), 'application/octet-stream')

            # Viewport should use the actual_target_width/height as images are resized
            xhtml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width={actual_target_width}, height={actual_target_height}"/>
    <title>{html_title}</title>
    <link href="stylesheet.css" rel="stylesheet" type="text/css"/>
</head>
<body><div><img src="images/{img_filename}" alt="{html_title}"/></div></body>
</html>"""
            create_file(os.path.join(oebps_dir, xhtml_filename), xhtml_content)

            manifest_items.append(f'<item id="{page_id_str if not is_cover_image_page else "cover"}" href="{xhtml_filename}" media-type="application/xhtml+xml"/>')
            spine_items.append(f'<itemref idref="{page_id_str if not is_cover_image_page else "cover"}"/>')
            manifest_items.append(f'<item id="{img_id_str}" {img_properties}href="images/{img_filename}" media-type="{media_type}"/>')
            
            page_list_for_nav.append(f'<li><a href="{xhtml_filename}">{html_title}</a></li>')


        nav_xhtml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><meta charset="UTF-8"/><title>Navigation</title></head>
<body>
    <nav epub:type="toc" id="toc"><h1>Table of Contents</h1><ol>{"".join(page_list_for_nav)}</ol></nav>
    <nav epub:type="page-list" hidden=""><h1>Page List</h1><ol>{"".join(page_list_for_nav)}</ol></nav>
</body></html>"""
        create_file(os.path.join(oebps_dir, "nav.xhtml"), nav_xhtml_content)
        manifest_items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')

        # Unique identifier
        book_id = f"urn:uuid:{custom_uuid or uuid.uuid4().hex}"
        
        # content.opf
        content_opf_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId" prefix="rendition: http://www.idpf.org/vocab/rendition/#">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>{epub_title or base_folder_name}</dc:title>
        <dc:language>{language_code}</dc:language>
        <dc:identifier id="BookId">{book_id}</dc:identifier>
        <dc:creator id="author">{epub_author}</dc:creator> 
        <meta property="dcterms:modified">{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}</meta>
        <meta name="cover" content="cover-image"/>
        <meta property="rendition:layout">pre-paginated</meta>
        <meta property="rendition:orientation">auto</meta>
        <meta property="rendition:spread">auto</meta>
    </metadata>
    <manifest>{chr(10).join(manifest_items)}</manifest>
    <spine>{chr(10).join(spine_items)}</spine>
</package>"""
        create_file(os.path.join(oebps_dir, "content.opf"), content_opf_content)

        # Create EPUB ZIP file
        print(f"Creating EPUB file: {output_epub_full_path}")
        os.makedirs(os.path.dirname(output_epub_full_path), exist_ok=True) # Ensure output directory exists
        with zipfile.ZipFile(output_epub_full_path, 'w', zipfile.ZIP_DEFLATED) as epub_zip:
            epub_zip.write(os.path.join(temp_dir, "mimetype"), "mimetype", compress_type=zipfile.ZIP_STORED)
            for root, _, files in os.walk(temp_dir):
                for file_name in files:
                    if file_name == "mimetype":
                        continue
                    file_path = os.path.join(root, file_name)
                    arcname = os.path.relpath(file_path, temp_dir)
                    epub_zip.write(file_path, arcname)
        
        print(f"EPUB successfully created: {output_epub_full_path}")
        return True

    except Exception as e:
        print(f"An error occurred during EPUB generation: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"Temporary directory cleaned up: {temp_dir}")
            except Exception as e:
                print(f"Warning: Failed to remove temporary directory {temp_dir}: {e}")

if __name__ == '__main__':
    # Example Usage (for testing epub_utils.py directly)
    print("Testing epub_utils.py...")
    # Create dummy image folders/files for testing
    test_source_dir = "test_epub_source"
    test_output_epub = "TestComic.epub"
    
    # Clean up previous test run
    if os.path.exists(test_source_dir):
        shutil.rmtree(test_source_dir)
    if os.path.exists(test_output_epub):
        os.remove(test_output_epub)
    if os.path.exists(f"temp_epub_build_{os.path.basename(test_source_dir)}"): # Simplified temp name for direct test
        shutil.rmtree(f"temp_epub_build_{os.path.basename(test_source_dir)}")


    os.makedirs(os.path.join(test_source_dir, "Chapter 01"), exist_ok=True)
    os.makedirs(os.path.join(test_source_dir, "Chapter 02"), exist_ok=True)

    try:
        # Create some dummy jpg files
        for i in range(3):
            img = Image.new('RGB', (800, 1200), color = 'red')
            img.save(os.path.join(test_source_dir, "Chapter 01", f"{i+1:03d}.jpg"))
        for i in range(2):
            img = Image.new('RGB', (900, 1300), color = 'blue')
            img.save(os.path.join(test_source_dir, "Chapter 02", f"{i+1:03d}.jpg"))

        print(f"Attempting to create EPUB: {test_output_epub} from {test_source_dir}")
        success = generate_epub_from_folder_content(
            source_folder_path=test_source_dir,
            output_epub_full_path=test_output_epub,
            epub_title="Test Comic Title",
            processing_mode='subfolder',
            language_code="en-US",
            epub_author="Test Author"
        )
        if success:
            print(f"Test EPUB '{test_output_epub}' created successfully.")
        else:
            print(f"Test EPUB creation failed.")

        # Test direct mode
        direct_source_dir = os.path.join(test_source_dir, "Chapter 01")
        direct_output_epub = "TestDirectChapter.epub"
        if os.path.exists(direct_output_epub): os.remove(direct_output_epub)

        print(f"\nAttempting to create EPUB (direct mode): {direct_output_epub} from {direct_source_dir}")
        success_direct = generate_epub_from_folder_content(
            source_folder_path=direct_source_dir,
            output_epub_full_path=direct_output_epub,
            epub_title="Test Chapter Title (Direct)",
            processing_mode='direct',
            language_code="en-US",
            epub_author="Direct Author",
            target_width_override=600,
            target_height_override=800
        )
        if success_direct:
            print(f"Test EPUB (direct mode) '{direct_output_epub}' created successfully.")
        else:
            print(f"Test EPUB (direct mode) creation failed.")


    except ImportError:
        print("Pillow (PIL) is not installed. Skipping direct test execution of epub_utils.py")
    except Exception as e:
        print(f"Error during test setup or execution: {e}")
    finally:
        # Clean up test files
        if os.path.exists(test_source_dir):
            shutil.rmtree(test_source_dir)
        # if os.path.exists(test_output_epub):
        #     os.remove(test_output_epub) # Keep generated for inspection
        # if os.path.exists(direct_output_epub):
        #     os.remove(direct_output_epub) # Keep for inspection
        print("\nepub_utils.py test finished.") 