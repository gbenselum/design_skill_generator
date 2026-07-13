import os
import urllib.request
import zipfile
import shutil

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def download_and_extract_zip(zip_url, output_dir, file_filters=None):
    """
    Downloads a zip file from a URL, extracts it, filters matching files,
    copies them to the output directory, and cleans up.
    """
    os.makedirs(output_dir, exist_ok=True)
    zip_path = "temp_font_archive.zip"
    temp_extract_dir = "temp_font_extracted"
    
    print(f"Downloading archive from {zip_url}...")
    req = urllib.request.Request(zip_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req) as response:
            with open(zip_path, 'wb') as f:
                f.write(response.read())
        print("Download complete.")
    except Exception as e:
        print(f"Failed to download archive: {e}")
        return False
        
    print("Extracting archive...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)
        print("Extraction complete.")
    except Exception as e:
        print(f"Failed to extract ZIP: {e}")
        # Clean up zip
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return False
        
    # Walk and match filters
    copied_count = 0
    for root, dirs, files in os.walk(temp_extract_dir):
        for file in files:
            if not file.endswith(('.ttf', '.woff2', '.woff')): continue
            
            should_copy = True
            if file_filters:
                should_copy = any(filt.lower() in file.lower() for filt in file_filters)
                
            if should_copy:
                src = os.path.join(root, file)
                dest = os.path.join(output_dir, file)
                shutil.copy2(src, dest)
                print(f"Extracted and saved: {file}")
                copied_count += 1
                
    # Cleanup
    if os.path.exists(zip_path):
        os.remove(zip_path)
    if os.path.exists(temp_extract_dir):
        shutil.rmtree(temp_extract_dir)
        
    print(f"Finished. Extracted {copied_count} fonts into {output_dir}.")
    return True

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python download_fonts.py [zip_url] [output_dir] [filter1,filter2,...]")
        print("Example: python download_fonts.py https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip skills/wise_design/fonts Regular,Medium,SemiBold,Bold")
    else:
        url = sys.argv[1]
        out = sys.argv[2]
        filters = sys.argv[3].split(',') if len(sys.argv) > 3 else None
        download_and_extract_zip(url, out, filters)
