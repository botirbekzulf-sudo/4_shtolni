// Настраивает проект Android, созданный командой "cap add android"
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const main = path.join(root, 'android', 'app', 'src', 'main');
const assets = path.join(root, 'assets');
const appId = JSON.parse(fs.readFileSync(path.join(root, 'capacitor.config.json'), 'utf8')).appId;

// Разрешения и горизонтальный экран
const manifestPath = path.join(main, 'AndroidManifest.xml');
let manifest = fs.readFileSync(manifestPath, 'utf8');
const perms = ['android.permission.RECORD_AUDIO', 'android.permission.MODIFY_AUDIO_SETTINGS']
  .filter(p => !manifest.includes(p))
  .map(p => `    <uses-permission android:name="${p}" />\n`).join('');
manifest = manifest.replace('</manifest>', `${perms}</manifest>`);
if (!manifest.includes('android:screenOrientation')) {
  manifest = manifest.replace(/<activity\b/, '<activity\n            android:screenOrientation="sensorLandscape"');
}
fs.writeFileSync(manifestPath, manifest);

// Весь экран без системных панелей, экран не гаснет
const javaDir = path.join(main, 'java', ...appId.split('.'));
fs.mkdirSync(javaDir, { recursive: true });
fs.writeFileSync(path.join(javaDir, 'MainActivity.java'), `package ${appId};

import android.os.Bundle;
import android.view.WindowManager;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (!hasFocus) return;
        WindowInsetsControllerCompat c = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        c.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
        c.hide(WindowInsetsCompat.Type.systemBars());
    }
}
`);

// Значок и заставка
const res = path.join(main, 'res');
for (const d of fs.readdirSync(res)) {
  const dir = path.join(res, d);
  if (d === 'mipmap-anydpi-v26') { fs.rmSync(dir, { recursive: true }); continue; }
  const m = d.match(/^mipmap-(\w+dpi)/);
  if (m) {
    const src = path.join(assets, `mipmap-${m[1]}.png`);
    for (const f of ['ic_launcher.png', 'ic_launcher_round.png', 'ic_launcher_foreground.png']) {
      if (fs.existsSync(path.join(dir, f))) fs.copyFileSync(src, path.join(dir, f));
    }
  }
  if (d.startsWith('drawable') && fs.existsSync(path.join(dir, 'splash.png'))) {
    fs.copyFileSync(path.join(assets, 'splash.png'), path.join(dir, 'splash.png'));
  }
}

// Номер версии растёт с каждой сборкой: Play не принимает повторный versionCode
const gradlePath = path.join(root, 'android', 'app', 'build.gradle');
const run = process.env.GITHUB_RUN_NUMBER || '1';
let gradle = fs.readFileSync(gradlePath, 'utf8');
gradle = gradle.replace(/versionCode\s+\d+/, `versionCode ${run}`).replace(/versionName\s+"[^"]*"/, `versionName "1.0.${run}"`);
fs.writeFileSync(gradlePath, gradle);
console.log('Проект Android настроен');
