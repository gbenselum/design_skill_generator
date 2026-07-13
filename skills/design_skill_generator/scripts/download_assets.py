import os
import json
import urllib.request
import urllib.error
import re
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def scan_obj_for_images(obj):
    """
    Recursively scans JSON dictionaries or lists for image URLs.
    """
    urls = []
    if isinstance(obj, dict):
        # Look for figmaImage block definition
        if obj.get('sys', {}).get('contentType', {}).get('sys', {}).get('id') == 'figmaImage':
            fields = obj.get('fields', {})
            url = fields.get('url')
            alt = fields.get('altText') or fields.get('figmaReference') or 'Design Asset'
            if url:
                urls.append((url, alt))
                
        # Fallback to direct URLs
        if 'url' in obj and isinstance(obj['url'], str):
            if 'figma-alpha-api' in obj['url'] or 's3-alpha' in obj['url'] or obj['url'].endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                urls.append((obj['url'], obj.get('altText') or 'Asset'))
                
        for k, v in obj.items():
            urls.extend(scan_obj_for_images(v))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(scan_obj_for_images(item))
            
    return urls

def run_downloader(input_dir, output_assets_dir, mapping_file_path):
    os.makedirs(output_assets_dir, exist_ok=True)
    url_to_local_map = {}
    image_index = 1
    
    if not os.path.exists(input_dir):
        print(f"Input directory does not exist: {input_dir}")
        return
        
    for category in os.listdir(input_dir):
        cat_path = os.path.join(input_dir, category)
        if not os.path.isdir(cat_path): continue
        
        for filename in sorted(os.listdir(cat_path)):
            if not filename.endswith('.json'): continue
            filepath = os.path.join(cat_path, filename)
            
            with open(filepath, 'r') as f:
                try:
                    data = json.load(f)
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
                    continue
                    
            page_slug = filename[:-5]
            found_images = scan_obj_for_images(data)
            
            for url, alt in found_images:
                if url in url_to_local_map: continue
                
                # Determine extension
                ext = ".png"
                if ".webp" in url: ext = ".webp"
                elif ".jpg" in url or ".jpeg" in url: ext = ".jpg"
                elif ".gif" in url: ext = ".gif"
                
                # Create clean filename
                clean_alt = re.sub(r'[^a-zA-Z0-9]', '_', alt).lower().strip('_')
                if len(clean_alt) > 30: clean_alt = clean_alt[:30]
                img_name = f"{category}_{page_slug}_{clean_alt}_{image_index}{ext}"
                
                local_path = os.path.join(output_assets_dir, img_name)
                print(f"Downloading: {url} -> {img_name}")
                
                req = urllib.request.Request(url, headers=HEADERS)
                try:
                    with urllib.request.urlopen(req) as response:
                        with open(local_path, 'wb') as f:
                            f.write(response.read())
                    url_to_local_map[url] = img_name
                    image_index += 1
                    time.sleep(0.1) # Citizen delay
                except urllib.error.HTTPError as e:
                    print(f"HTTP Error {e.code} for {url}")
                except Exception as e:
                    print(f"Failed to download {url}: {e}")
                    
    with open(mapping_file_path, 'w') as f:
        json.dump(url_to_local_map, f, indent=2)
        
    print(f"Download finished. {len(url_to_local_map)} assets saved in {output_assets_dir}.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: python download_assets.py [input_dir] [output_assets_dir] [mapping_file_json]")
        print("Example: python download_assets.py raw_data skills/wise_design/assets url_to_assets_map.json")
    else:
        run_downloader(sys.argv[1], sys.argv[2], sys.argv[3])
