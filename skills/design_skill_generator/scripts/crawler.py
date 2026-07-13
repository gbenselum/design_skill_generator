import os
import re
import json
import time
import urllib.request
import urllib.error

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_page_data(url, cache_dir="cache"):
    """
    Fetch a page and extract the Next.js __NEXT_DATA__ JSON payload.
    Uses a local disk cache to avoid redundant hits.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_key = re.sub(r'[^a-zA-Z0-9]', '_', url) + ".json"
    cache_path = os.path.join(cache_dir, cache_key)
    
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return json.load(f)
            
    print(f"Fetching: {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            
        # Parse Next.js static JSON block
        pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(pattern, html)
        if match:
            json_str = match.group(1)
            data = json.loads(json_str)
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
            time.sleep(0.5) # Citizen delay
            return data
        else:
            print(f"Warning: No __NEXT_DATA__ found for {url}")
            return None
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code} for URL: {url}")
        return None
    except Exception as e:
        print(f"Error fetching URL {url}: {e}")
        return None

def extract_nested_paths(pages_list, target_prefixes):
    """
    Recursively filters a list of pages/routes from the __NEXT_DATA__ layout.
    """
    matched_slugs = []
    
    def walk_tree(items):
        if not items: return
        for item in items:
            slug = item.get('slug') or item.get('uri') or ''
            slug = slug.strip('/')
            
            # Check if slug matches target prefixes
            for pref in target_prefixes:
                if slug.startswith(pref) and slug not in matched_slugs:
                    matched_slugs.append(slug)
                    
            walk_tree(item.get('pages', []))
            
    walk_tree(pages_list)
    return matched_slugs

def run_crawler(base_url, target_prefixes, output_dir="raw_data"):
    """
    Crawls and extracts structured JSON content for all subpages matching the prefixes.
    """
    base_url = base_url.rstrip('/')
    print(f"Starting crawl of {base_url} with sections: {target_prefixes}")
    
    # 1. Fetch homepage to get page navigation tree
    home_data = get_page_data(base_url)
    if not home_data:
        print("Failed to fetch starting URL configuration.")
        return
        
    props = home_data.get('props', {})
    page_props = props.get('pageProps', {})
    navigation = page_props.get('pages') or page_props.get('navigation') or []
    
    if not navigation:
        # Check alternative locations in NextJS payload
        navigation = props.get('pages') or props.get('navigation') or []
        
    slugs = extract_nested_paths(navigation, target_prefixes)
    print(f"Found {len(slugs)} routes matching filters: {slugs}")
    
    # 2. Crawl routes
    for slug in slugs:
        page_url = f"{base_url}/{slug}"
        print(f"Crawling route: {slug}")
        data = get_page_data(page_url)
        if not data: continue
        
        # Save page payload (nested under pageProps)
        page_content = data.get('props', {}).get('pageProps', {}).get('page')
        if not page_content:
            # Fallback to whole payload if page is flat
            page_content = data.get('props', {}).get('pageProps', data)
            
        # Determine output folder
        category = "general"
        for pref in target_prefixes:
            if slug.startswith(pref):
                category = pref
                break
                
        cat_dir = os.path.join(output_dir, category)
        os.makedirs(cat_dir, exist_ok=True)
        
        file_name = slug.replace(category + "/", "").replace("/", "-") + ".json"
        with open(os.path.join(cat_dir, file_name), 'w') as f:
            json.dump(page_content, f, indent=2)
            
    print("Crawl complete. Pages saved.")

if __name__ == "__main__":
    # Example usage targeting a Next.js documentation portal
    import sys
    if len(sys.argv) < 3:
        print("Usage: python crawler.py [base_url] [section1,section2,...]")
        print("Example: python crawler.py https://docs.wise.design/ foundations,components,patterns")
    else:
        base = sys.argv[1]
        sections = sys.argv[2].split(',')
        run_crawler(base, sections)
