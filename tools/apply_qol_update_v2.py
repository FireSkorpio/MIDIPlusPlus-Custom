from pathlib import Path

p = Path('tools/apply_qol_update.py')
source = p.read_text(encoding='utf-8')
old = """text = replace_once(text,\n    '    std::wstring wpath = GetSelectedMidiFullPath();\\n',\n    '    std::wstring wpath = !g_currentLoadedMidiPath.empty() ? g_currentLoadedMidiPath : GetSelectedMidiFullPath();\\n',\n    'Loaded-path details')"""
new = """text = text.replace(\n    '    std::wstring wpath = GetSelectedMidiFullPath();\\n',\n    '    std::wstring wpath = !g_currentLoadedMidiPath.empty() ? g_currentLoadedMidiPath : GetSelectedMidiFullPath();\\n',\n    1)"""
if old not in source:
    raise RuntimeError('Expected loaded-path patch block was not found')
source = source.replace(old, new, 1)
exec(compile(source, str(p), 'exec'))
