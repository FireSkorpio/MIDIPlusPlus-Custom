from pathlib import Path

p = Path('tools/apply_qol_update.py')
source = p.read_text(encoding='utf-8')

old = """text = replace_once(text,\n    '    std::wstring wpath = GetSelectedMidiFullPath();\\n',\n    '    std::wstring wpath = !g_currentLoadedMidiPath.empty() ? g_currentLoadedMidiPath : GetSelectedMidiFullPath();\\n',\n    'Loaded-path details')"""
new = """text = text.replace(\n    '    std::wstring wpath = GetSelectedMidiFullPath();\\n',\n    '    std::wstring wpath = !g_currentLoadedMidiPath.empty() ? g_currentLoadedMidiPath : GetSelectedMidiFullPath();\\n',\n    1)"""
if old not in source:
    raise RuntimeError('Expected loaded-path patch block was not found')
source = source.replace(old, new, 1)

old_drop = """text = insert_before(text, wm_command_marker, drop_case, 'Drag-drop handler')"""
new_drop = """wndproc_pos = text.find('static LRESULT CALLBACK WndProc(HWND hWnd')\nif wndproc_pos < 0:\n    raise RuntimeError('Main WndProc marker not found')\ncommand_pos = text.find(wm_command_marker, wndproc_pos)\nif command_pos < 0:\n    raise RuntimeError('Main WndProc WM_COMMAND marker not found')\ntext = text[:command_pos] + drop_case + text[command_pos:]"""
if old_drop not in source:
    raise RuntimeError('Expected drag-drop patch line was not found')
source = source.replace(old_drop, new_drop, 1)

exec(compile(source, str(p), 'exec'))
