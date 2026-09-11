import sys
import subprocess
from caption_app.config import ROOT

if __name__ == '__main__':
    (ROOT / 'logs').mkdir(exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(ROOT / 'logs' / 'app.log', 'a', encoding='utf-8', buffering=1)
        sys.stderr = sys.stdout
    from caption_app.updater import apply_pending, update_lock
    try:
        with update_lock(ROOT, 'instance.lock'):
            try:
                updated = apply_pending(ROOT)
            except Exception as exc:
                print(f'Update deferred: {exc}', flush=True)
                updated = False
            if not updated:
                from caption_app.ui import main
                raise SystemExit(main())
        # Release the instance lock before starting the updated code.
        subprocess.Popen([sys.executable, '-s', '-X', 'utf8', str(ROOT / 'main.py')])
    except OSError as exc:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication([])
        QMessageBox.information(None, 'Translate Anything',
                                f'The app may already be open. Close the other instance and try again.\n{exc}')
