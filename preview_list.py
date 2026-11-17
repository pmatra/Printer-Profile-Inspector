import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('inspector', Path(__file__).resolve().parent / 'inspector.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
app = m.Inspector()
app.title('ICC Gamut Inspector — Profile List Preview')
app.main_tabs.select(app.list_tab)
app.mainloop()
