const VirtualMachine = require('scratch-vm');
const {ScratchStorage, AssetType} = require('scratch-storage');
const JSZip = require('jszip');
const fs = require('fs');

const SB3 = process.argv[2];
const SECONDS = Number(process.argv[3] || 60);
const CLICK = process.argv[4] || ''; // "x,y,second" stage coords, 1-based second

function makeRenderer() {
  let nextId = 1;
  const noop = () => undefined;
  return new Proxy(
    {},
    {
      get(_t, prop) {
        if (prop === 'createDrawable') return () => nextId++;
        if (prop === 'nativeSize' || prop === 'getNativeSize') return () => [480, 360];
        if (prop === 'createBitmapSkin') return () => 'skin';
        if (prop === 'createSVGSkin') return () => 'skin';
        if (prop === 'getSkinSize') return () => [100, 100];
        if (prop === 'getCurrentSkinSize') return () => [100, 100];
        if (prop === 'getFencedPositionOfDrawable')
          return (_id, pos) => [Math.max(-240, Math.min(240, pos[0])), Math.max(-180, Math.min(180, pos[1]))];
        if (prop === 'getSkinRotationCenter') return () => [50, 50];
        if (prop === 'isTouchingColor' || prop === 'colorAtPoint') return () => false;
        if (prop === 'getBounds' || prop === 'getBoundsForBubble')
          return () => ({left: -50, right: 50, top: 50, bottom: -50});
        return noop;
      },
    }
  );
}

function makeAudio() {
  const bank = new Proxy(
    {
      addSoundPlayer: () => undefined,
      getSoundIndex: () => 0,
      playSound: () => Promise.resolve({target: null, sound: null}),
      stopSoundForTarget: () => undefined,
      stopAllSounds: () => undefined,
      isPlaying: () => false,
    },
    {get: (t, p) => (p in t ? t[p] : () => Promise.resolve())}
  );
  return new Proxy(
    {
      soundBank: bank,
      createBank: () => bank,
      decodeSoundPlayer: sound =>
        Promise.resolve({id: sound.md5 || 's', buffer: {sampleRate: 22050, length: 1}}),
      createAudioEngine: () => Promise.resolve(),
      activateAudioEngine: () => Promise.resolve(),
    },
    {get: (t, p) => (p in t ? t[p] : () => Promise.resolve())}
  );
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const TINY_PNG =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
  global.createImageBitmap = async () => ({width: 100, height: 100});
  global.document = {
    createElement: () => ({
      width: 0,
      height: 0,
      style: {},
      toDataURL: () => TINY_PNG,
      getContext: () => ({drawImage: () => undefined}),
    }),
  };

  const zipBuf = fs.readFileSync(SB3);
  const zip = await JSZip.loadAsync(zipBuf);

  const storage = new ScratchStorage();
  storage.addWebStore(Object.values(AssetType), async (assetId, dataFormat) => {
    const entry = zip.file(`${assetId}.${dataFormat}`);
    if (!entry) return null;
    const buf = await entry.async('nodebuffer');
    return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  });

  const vm = new VirtualMachine();
  vm.attachStorage(storage);
  vm.attachRenderer(makeRenderer());
  vm.attachAudioEngine(makeAudio());
  vm.attachV2BitmapAdapter({
    resize: canvas => canvas,
    convertDataURIToBinary: dataURI => Buffer.from(dataURI.split(',')[1], 'base64'),
  });

  process.on('uncaughtException', err => {
    console.error('UNCAUGHT:', err && err.stack ? err.stack : err);
    process.exit(1);
  });

  const ab = zipBuf.buffer.slice(zipBuf.byteOffset, zipBuf.byteOffset + zipBuf.byteLength);
  await vm.loadProject(ab);

  let click = null;
  if (CLICK) {
    const [x, y, sec] = CLICK.split(',').map(Number);
    click = {x, y, sec};
  }

  vm.runtime.currentStepTime = 1000 / 30;
  vm.greenFlag();

  const totalFrames = SECONDS * 30;
  const start = Date.now();
  let clickDone = !click;
  for (let frame = 1; frame <= totalFrames; frame++) {
    const elapsed = (Date.now() - start) / 1000;
    if (!clickDone && elapsed >= click.sec) {
      try {
        vm.postIOData('mouse', {
          x: click.x,
          y: click.y,
          isDown: true,
          button: 'left',
          timestamp: Date.now(),
        });
        vm.postIOData('mouse', {x: click.x, y: click.y, isDown: false, timestamp: Date.now()});
        clickDone = true;
        console.log(`CLICK at ${elapsed.toFixed(1)}s at (${click.x},${click.y})`);
      } catch (err) {
        console.error(`CLICK FAILED at ${elapsed.toFixed(1)}s:`);
        console.error(err && err.stack ? err.stack : err);
        process.exit(1);
      }
    }
    try {
      vm.runtime._step();
    } catch (err) {
      console.error(`CRASH at frame ${frame} (${elapsed.toFixed(1)}s):`);
      console.error(err && err.stack ? err.stack : err);
      process.exit(1);
    }
    const drift = 1000 / 30 - (Date.now() - (start + (frame - 1) * (1000 / 30)));
    if (drift > 0) await sleep(drift);
  }

  const stageTarget = vm.runtime.getTargetForStage();
  const clones = vm.runtime.targets.filter(t => !t.isOriginal);
  console.log('NO CRASH in', SECONDS, 'seconds');
  console.log(
    'stage vars:',
    JSON.stringify(Object.values(stageTarget.variables).map(v => [v.name, v.value]))
  );
  const alive = vm.runtime.threads.filter(t => t.status !== 4);
  console.log('threads alive:', alive.length, 'total:', vm.runtime.threads.length);
  console.log(
    'thread sample:',
    alive.slice(0, 4).map(t => `${t.target && t.target.getName()} s=${t.status}`).join(' | ')
  );
  console.log('targets =', vm.runtime.targets.length, 'clones =', clones.length);
  console.log(
    'costumes:',
    vm.runtime.targets.map(t => `${t.getName()}[${t.currentCostume}]`).join(' ')
  );
}

main().catch(err => {
  console.error('LOAD/RUN FAILED:', err && err.stack ? err.stack : err);
  process.exit(1);
});
