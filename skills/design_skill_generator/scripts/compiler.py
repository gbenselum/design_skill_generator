import os
import json
import re

def clean_text(text_obj):
    """
    Recursively converts standard headless CMS / Contentful Rich Text structures
    into clean Markdown format.
    """
    if not text_obj:
        return ""
    if isinstance(text_obj, str):
        return text_obj.strip()
    if isinstance(text_obj, dict):
        node_type = text_obj.get('nodeType', '')
        
        # Text Node
        if node_type == 'text':
            val = text_obj.get('value', '')
            marks = [m.get('type') for m in text_obj.get('marks', []) if isinstance(m, dict)]
            if 'bold' in marks:
                val = f"**{val}**"
            if 'underline' in marks:
                val = f"<u>{val}</u>"
            return val
            
        # Hyperlinks & Entry references
        if 'hyperlink' in node_type or 'entry' in node_type or 'asset' in node_type:
            uri = text_obj.get('data', {}).get('uri', '')
            label = ""
            for child in text_obj.get('content', []):
                label += clean_text(child)
            if uri:
                return f"[{label if label else uri}]({uri})"
            return label
            
        # Container Nodes
        children = text_obj.get('content', [])
        result = ""
        for child in children:
            result += clean_text(child)
            
        if node_type == 'paragraph':
            return result + "\n\n"
        elif node_type == 'list-item':
            result_clean = result.strip().replace('\n\n', '\n')
            return f"- {result_clean}\n"
        elif node_type == 'unordered-list':
            return result + "\n"
        elif node_type == 'ordered-list':
            return result + "\n"
        elif node_type.startswith('heading-'):
            try:
                level = int(node_type.split('-')[-1])
            except ValueError:
                level = 3
            return f"\n{'#' * (level + 2)} {result.strip()}\n\n"
        elif node_type == 'document':
            return result
            
        return result
        
    if isinstance(text_obj, list):
        return "".join([clean_text(item) for item in text_obj])
        
    return str(text_obj)

def parse_table(table_block):
    """
    Parses structural table blocks into standard Markdown table format.
    """
    if not table_block: return ""
    fields = table_block.get('fields', {})
    rows = fields.get('rows', [])
    if not rows: return ""
    
    markdown = ""
    has_header = fields.get('hasHeader', True)
    
    header_cells = []
    if has_header and len(rows) > 0:
        header_cells = [clean_text(c.get('fields', {}).get('body', '')).strip().replace('\n', '<br>') for c in rows[0].get('fields', {}).get('cells', [])]
        start_row = 1
    else:
        if len(rows) > 0:
            first_row_cells = rows[0].get('fields', {}).get('cells', [])
            header_cells = [f"Col {i+1}" for i in range(len(first_row_cells))]
        start_row = 0
        
    if not header_cells: return ""
    
    markdown += "| " + " | ".join(header_cells) + " |\n"
    markdown += "| " + " | ".join(["---"] * len(header_cells)) + " |\n"
    
    for r in rows[start_row:]:
        cells = [clean_text(c.get('fields', {}).get('body', '')).strip().replace('\n', '<br>') for c in r.get('fields', {}).get('cells', [])]
        if cells:
            while len(cells) < len(header_cells):
                cells.append("")
            markdown += "| " + " | ".join(cells[:len(header_cells)]) + " |\n"
            
    return markdown

def render_figma_images(block, url_to_assets_map):
    """
    Finds and replaces image links with local asset references.
    """
    if not block: return ""
    b_type = block.get('sys', {}).get('contentType', {}).get('sys', {}).get('id')
    bf = block.get('fields', {})
    
    if b_type == 'figmaImage':
        url = bf.get('url')
        alt = bf.get('altText') or bf.get('figmaReference') or 'Design Preview'
        local_name = url_to_assets_map.get(url)
        if local_name:
            return f"![{alt}](../assets/{local_name})\n\n"
            
    if b_type == 'multipleFigmaImages':
        markdown = ""
        for ref in bf.get('figmaReferences', []):
            markdown += render_figma_images(ref, url_to_assets_map)
        return markdown
        
    return ""

def compile_category(category_name, input_dir, output_file, url_to_assets_map):
    cat_dir = os.path.join(input_dir, category_name)
    if not os.path.exists(cat_dir):
        print(f"Category folder not found: {cat_dir}")
        return
        
    md_content = f"# Design System - {category_name.title()}\n\nThis guide covers the {category_name} references of the visual identity.\n\n"
    
    filenames = sorted(os.listdir(cat_dir))
    for filename in filenames:
        if not filename.endswith('.json'): continue
        filepath = os.path.join(cat_dir, filename)
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        title = data.get('title', filename[:-5].replace("-", " ").title())
        md_content += f"## {title}\n\n"
        
        # Load header
        header = data.get('header', {})
        if isinstance(header, dict):
            sub = header.get('fields', {}).get('subHeader')
            if sub:
                md_content += f"{clean_text(sub)}\n\n"
            h_img = header.get('fields', {}).get('image')
            if h_img:
                md_content += render_figma_images(h_img, url_to_assets_map)
                
        # Parse content sections
        sections = data.get('sections', [])
        for sec in sections:
            if not sec: continue
            sec_fields = sec.get('fields', {})
            sec_title = sec_fields.get('title')
            if sec_title:
                md_content += f"### {sec_title}\n\n"
            sec_content = sec_fields.get('content')
            if sec_content:
                md_content += f"{clean_text(sec_content)}\n\n"
                
            # Parse nested blocks
            for b in sec_fields.get('blocks', []):
                if not b: continue
                bf = b.get('fields', {})
                b_type = b.get('sys', {}).get('contentType', {}).get('sys', {}).get('id')
                
                # Image embed
                img_md = render_figma_images(b, url_to_assets_map)
                if img_md:
                    md_content += img_md
                    
                if b_type == 'table':
                    md_content += parse_table(b) + "\n"
                elif b_type == 'colorBlocks':
                    md_content += f"#### {bf.get('title', 'Colors')}\n\n"
                    md_content += "| Color Name | Hex (Light) | Hex (Dark) | Token | Description |\n"
                    md_content += "| --- | --- | --- | --- | --- |\n"
                    for item in bf.get('colorBlockItems', []):
                        itf = item.get('fields', {})
                        if itf.get('useAsBlank'): continue
                        name = itf.get('colorName') or itf.get('captionTitle') or 'Color'
                        hex_light = itf.get('hex', '')
                        hex_dark = itf.get('hexDarkMode', '')
                        token = itf.get('backgroundToken') or itf.get('colorToken', '')
                        desc = itf.get('captionBody', '').replace('\n', '<br>')
                        md_content += f"| {name} | `{hex_light}` | `{hex_dark}` | `{token}` | {desc} |\n"
                    md_content += "\n"
                elif b_type == 'section':
                    nest_title = bf.get('title')
                    if nest_title:
                        md_content += f"#### {nest_title}\n\n"
                    if bf.get('content'):
                        md_content += f"{clean_text(bf.get('content'))}\n\n"
                    for nest_b in bf.get('blocks', []):
                        if not nest_b: continue
                        nest_img = render_figma_images(nest_b, url_to_assets_map)
                        if nest_img:
                            md_content += nest_img
                        if nest_b.get('sys', {}).get('contentType', {}).get('sys', {}).get('id') == 'table':
                            md_content += parse_table(nest_b) + "\n"
        md_content += "---\n\n"
        
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"Category compile complete: {output_file}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 5:
        print("Usage: python compiler.py [category_name] [input_dir] [output_file] [assets_map_json]")
        print("Example: python compiler.py components raw_data references/components.md url_to_assets_map.json")
    else:
        cat = sys.argv[1]
        inp = sys.argv[2]
        out = sys.argv[3]
        map_path = sys.argv[4]
        
        asset_map = {}
        if os.path.exists(map_path):
            with open(map_path, 'r') as f:
                asset_map = json.load(f)
                
        compile_category(cat, inp, out, asset_map)
