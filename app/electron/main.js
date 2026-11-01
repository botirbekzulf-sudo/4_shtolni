const { app, BrowserWindow, session } = require('electron');
const path = require('path');

function createWindow() {
  const allowed = new Set(['media', 'pointerLock', 'fullscreen', 'clipboard-sanitized-write']);
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => cb(allowed.has(permission)));
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => allowed.has(permission));

  const win = new BrowserWindow({
    width: 1280,
    height: 720,
    backgroundColor: '#0d100b',
    autoHideMenuBar: true,
    title: 'Четыре Штольни',
    webPreferences: { contextIsolation: true, nodeIntegration: false, backgroundThrottling: false }
  });
  win.setMenu(null);
  win.maximize();
  win.loadFile(path.join(__dirname, '..', 'www', 'index.html'));
  win.webContents.on('before-input-event', (_e, input) => {
    if (input.type === 'keyDown' && input.key === 'F11') win.setFullScreen(!win.isFullScreen());
  });
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());
