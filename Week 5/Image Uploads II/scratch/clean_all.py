import os
import re

def clean_python(content):
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if ' #' in line:
            parts = line.split(' #', 1)
            quotes1 = parts[0].count("'")
            quotes2 = parts[0].count('"')
            if quotes1 % 2 == 0 and quotes2 % 2 == 0:
                line = parts[0]
        new_lines.append(line)
    return '\n'.join(new_lines)

def clean_tf(content):
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('//'):
            continue
        if ' #' in line:
            parts = line.split(' #', 1)
            if parts[0].count('"') % 2 == 0:
                line = parts[0]
        if ' //' in line:
            parts = line.split(' //', 1)
            if parts[0].count('"') % 2 == 0:
                line = parts[0]
        new_lines.append(line.rstrip())
    return '\n'.join(new_lines)

def clean_html(content):
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('//'):
            continue
        if '//' in line and 'http://' not in line and 'https://' not in line:
            parts = line.split('//', 1)
            if parts[0].count('"') % 2 == 0 and parts[0].count("'") % 2 == 0:
                line = parts[0]
        new_lines.append(line)
    return '\n'.join(new_lines)

def clean_file(filepath):
    print(f"Cleaning comments from: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    ext = os.path.splitext(filepath)[1]
    if ext == '.py':
        cleaned = clean_python(content)
    elif ext == '.tf':
        cleaned = clean_tf(content)
    elif filepath.endswith('.tftpl') or ext in ['.html', '.js']:
        cleaned = clean_html(content)
    else:
        cleaned = content
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(cleaned)

def main():
    root_dir = r"c:\Users\Vaibhav.S.P\Downloads\TringApps Intern\Week 5\Image Uploads II"
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            if '.terraform' in dirpath or '.git' in dirpath:
                continue
            ext = os.path.splitext(f)[1]
            if ext not in ['.py', '.tf', '.html', '.tftpl', '.js']:
                continue
            filepath = os.path.join(dirpath, f)
            clean_file(filepath)

if __name__ == '__main__':
    main()
