"""Run unit checks with the same bundled dependencies used by the renderer."""
from document_runtime import bootstrap
if __name__=='__main__':
    bootstrap()
    import unittest
    from pathlib import Path
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1]/'tests'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
