import ctypes, sys, time
from PIL import ImageGrab
u=ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)
time.sleep(3)
h=u.FindWindowW(None,"AMBOSS → Anki Queue")
r=ctypes.wintypes.RECT() if hasattr(ctypes,'wintypes') else None
import ctypes.wintypes as w
r=w.RECT(); u.GetWindowRect(h,ctypes.byref(r))
ImageGrab.grab((r.left,r.top,r.right,r.bottom)).save(sys.argv[1])
