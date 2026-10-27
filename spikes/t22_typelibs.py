"""T22 spike: which type libraries does LIRA register, and where are their files?"""

import winreg

import pythoncom

with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "TypeLib") as root:
    for i in range(winreg.QueryInfoKey(root)[0]):
        guid = winreg.EnumKey(root, i)
        with winreg.OpenKey(root, guid) as g:
            for j in range(winreg.QueryInfoKey(g)[0]):
                ver = winreg.EnumKey(g, j)
                try:
                    name = winreg.QueryValue(g, ver)
                except OSError:
                    continue
                if "lira" not in name.lower() and "sapr" not in name.lower():
                    continue
                paths = {}
                for arch in ("win64", "win32"):
                    try:
                        paths[arch] = winreg.QueryValue(g, rf"{ver}\0\{arch}")
                    except OSError:
                        pass
                print(guid, ver, repr(name), paths)
                for arch, path in paths.items():
                    try:
                        tlib = pythoncom.LoadTypeLib(path)
                        kinds = [tlib.GetTypeInfoType(k) for k in range(tlib.GetTypeInfoCount())]
                        coclasses = [tlib.GetDocumentation(k)[0] for k, t in enumerate(kinds)
                                     if t == pythoncom.TKIND_COCLASS]
                        print("   ", arch, "types", len(kinds), "coclasses", coclasses)
                    except Exception as exc:
                        print("   ", arch, "load failed", exc)
