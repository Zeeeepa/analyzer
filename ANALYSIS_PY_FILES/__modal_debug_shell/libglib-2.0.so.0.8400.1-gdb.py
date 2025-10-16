import sys
import gdb

# Update module path.
dir_ = '/__modal/.debug_shell/nix/store/31bcivh2cff29h1gg85m29v0y51f1rij-glib-2.84.1/share/glib-2.0/gdb'
if not dir_ in sys.path:
    sys.path.insert(0, dir_)

from glib_gdb import register
register (gdb.current_objfile ())
