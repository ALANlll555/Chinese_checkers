/**
 * 跳棋 — Web Audio API 音效引擎 + 背景音乐生成器
 * 全部程序化合成，零外部文件依赖
 */

const AudioEngine = (() => {
  let ctx = null;
  let bgmGain = null;
  let sfxGain = null;
  let bgmActive = false;
  let bgmTimeout = null;
  let currentStyle = 'piano';       // 'ambient'|'piano'|'8bit'|'lofi'
  let bgmVolume = 0.3;
  let sfxVolume = 0.6;
  let _initialized = false;

  // ── 初始化（首次用户交互时调用） ──────────────

  function _ensureCtx() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      bgmGain = ctx.createGain();
      bgmGain.gain.value = bgmVolume;
      bgmGain.connect(ctx.destination);
      sfxGain = ctx.createGain();
      sfxGain.gain.value = sfxVolume;
      sfxGain.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  // ── 音效（短促合成音） ────────────────────────

  function _playTone(freq, type, duration, gainVal = 0.3, glideTo = null) {
    _ensureCtx();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, now);
    if (glideTo) osc.frequency.linearRampToValueAtTime(glideTo, now + duration);
    g.gain.setValueAtTime(gainVal, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + duration);
    osc.connect(g);
    g.connect(sfxGain);
    osc.start(now);
    osc.stop(now + duration);
  }

  function _playNoise(duration, gainVal = 0.15) {
    _ensureCtx();
    const now = ctx.currentTime;
    const bufferSize = ctx.sampleRate * duration;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const g = ctx.createGain();
    g.gain.setValueAtTime(gainVal, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + duration);
    const filter = ctx.createBiquadFilter();
    filter.type = 'highpass';
    filter.frequency.value = 2000;
    source.connect(filter);
    filter.connect(g);
    g.connect(sfxGain);
    source.start(now);
    source.stop(now + duration);
  }

  function playSelect() { _playTone(660, 'sine', 0.08, 0.25); }
  function playMove() { _playTone(440, 'triangle', 0.12, 0.3, 520); }
  function playJump() {
    _ensureCtx();
    const now = ctx.currentTime;
    [440, 554, 659].forEach((f, i) => {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(f, now + i * 0.05);
      g.gain.setValueAtTime(0.22, now + i * 0.05);
      g.gain.exponentialRampToValueAtTime(0.001, now + i * 0.05 + 0.08);
      osc.connect(g);
      g.connect(sfxGain);
      osc.start(now + i * 0.05);
      osc.stop(now + i * 0.05 + 0.08);
    });
  }
  function playVictory() {
    _ensureCtx();
    const now = ctx.currentTime;
    [523, 659, 784, 1047].forEach((f, i) => {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(f, now + i * 0.15);
      g.gain.setValueAtTime(0.35, now + i * 0.15);
      g.gain.exponentialRampToValueAtTime(0.001, now + i * 0.15 + 0.25);
      osc.connect(g);
      g.connect(sfxGain);
      osc.start(now + i * 0.15);
      osc.stop(now + i * 0.15 + 0.25);
    });
  }
  function playUndo() { _playTone(440, 'triangle', 0.1, 0.25, 330); }
  function playClick() { _playNoise(0.02, 0.12); }
  function playInvalid() { _playTone(200, 'sawtooth', 0.15, 0.2); }

  // ── 背景音乐生成器 ────────────────────────────

  /**
   * 环境音风格：柔和音垫
   * 低频滤波锯齿波，缓慢和声变化
   */
  function _bgmAmbient() {
    _ensureCtx();
    const now = ctx.currentTime;
    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const g = ctx.createGain();
    const filter = ctx.createBiquadFilter();

    osc1.type = 'sawtooth';
    osc2.type = 'sawtooth';
    osc1.frequency.value = 110;
    osc2.frequency.value = 165;
    filter.type = 'lowpass';
    filter.frequency.value = 400;
    filter.Q.value = 1;
    g.gain.value = 0.08;

    // 缓慢频率漂移
    osc1.frequency.linearRampToValueAtTime(116, now + 4);
    osc2.frequency.linearRampToValueAtTime(172, now + 4);
    osc1.frequency.linearRampToValueAtTime(110, now + 8);
    osc2.frequency.linearRampToValueAtTime(165, now + 8);

    osc1.connect(filter);
    osc2.connect(filter);
    filter.connect(g);
    g.connect(bgmGain);
    osc1.start(now);
    osc2.start(now);

    return { oscillators: [osc1, osc2], filter, gain: g };
  }

  /**
   * 钢琴风格：稀疏单音旋律
   * 简单正弦波，间隔2秒
   */
  let _minimalNotes = null;
  function _bgmPiano() {
    _ensureCtx();
    const notes = [262, 294, 330, 349, 392, 349, 330, 294]; // C D E F G F E D
    let idx = 0;

    function playNote() {
      if (!bgmActive) return;
      _ensureCtx();
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = notes[idx % notes.length];
      g.gain.setValueAtTime(0.0, now);
      g.gain.linearRampToValueAtTime(0.15, now + 0.05);
      g.gain.exponentialRampToValueAtTime(0.001, now + 1.8);
      osc.connect(g);
      g.connect(bgmGain);
      osc.start(now);
      osc.stop(now + 2.0);
      idx++;
      if (bgmActive) bgmTimeout = setTimeout(playNote, 2200);
    }
    playNote();
    return { stop: () => clearTimeout(bgmTimeout) };
  }

  /**
   * 8-bit 风格：欢快芯片旋律
   * 方波，快节奏 130BPM
   */
  let _cartoonNotes = null;
  function _bgm8bit() {
    _ensureCtx();
    // 超级马里奥风格上行旋律
    const melody = [
      { f: 659, d: 0.12 }, { f: 659, d: 0.12 }, null, { f: 659, d: 0.12 },
      null, { f: 523, d: 0.12 }, { f: 659, d: 0.12 }, null,
      { f: 784, d: 0.25 }, null, null, { f: 392, d: 0.25 }, null, null,
      { f: 523, d: 0.18 }, null, { f: 392, d: 0.18 }, null, { f: 330, d: 0.18 },
      null, { f: 440, d: 0.12 }, null, { f: 494, d: 0.12 },
      null, { f: 466, d: 0.12 }, { f: 440, d: 0.12 }, null,
      { f: 392, d: 0.12 }, { f: 659, d: 0.12 }, { f: 784, d: 0.12 },
      null, { f: 880, d: 0.12 }, null, { f: 698, d: 0.12 },
      { f: 784, d: 0.12 }, null, { f: 659, d: 0.12 },
      null, { f: 523, d: 0.12 }, { f: 587, d: 0.12 }, { f: 494, d: 0.12 },
    ];

    const bpm = 163;  // 1.25x 倍速
    const beatDur = 60 / bpm;
    let idx = 0;

    function playStep() {
      if (!bgmActive) return;
      _ensureCtx();
      const now = ctx.currentTime;
      const n = melody[idx % melody.length];
      if (n) {
        const osc = ctx.createOscillator();
        const g = ctx.createGain();
        osc.type = 'square';
        osc.frequency.value = n.f;
        g.gain.setValueAtTime(0.0, now);
        g.gain.linearRampToValueAtTime(0.12, now + 0.01);
        g.gain.exponentialRampToValueAtTime(0.001, now + n.d);
        osc.connect(g);
        g.connect(bgmGain);
        osc.start(now);
        osc.stop(now + n.d + 0.05);
      }
      idx++;
      if (bgmActive) bgmTimeout = setTimeout(playStep, beatDur * 1000);
    }
    playStep();
    return { stop: () => clearTimeout(bgmTimeout) };
  }

  /**
   * Lo-fi 风格：舒缓爵士和弦 + 低保真噪音
   * 正弦波 + 低通滤波 + 白噪声底噪，60 BPM
   */
  let _lofiHandle = null;
  function _bgmLofi() {
    _ensureCtx();
    // 爵士和弦进行：ii7 - V7 - Imaj7 (Dm7 - G7 - Cmaj7)
    const chords = [
      { root: 146.83, thirds: [175, 220, 293.66] },   // Dm7: D F A C
      { root: 196,   thirds: [246.94, 293.66, 369.99] }, // G7: G B D F
      { root: 130.81, thirds: [164.81, 196, 261.63] },   // Cmaj7: C E G B
      { root: 130.81, thirds: [164.81, 196, 261.63] },   // Cmaj7 (hold)
    ];

    // 白噪声底噪（模拟 vinyl crackle）
    const noiseBuf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    const nd = noiseBuf.getChannelData(0);
    for (let i = 0; i < nd.length; i++) nd[i] = (Math.random() * 2 - 1) * 0.015;
    const noiseSrc = ctx.createBufferSource();
    noiseSrc.buffer = noiseBuf;
    noiseSrc.loop = true;
    const noiseG = ctx.createGain();
    noiseG.gain.value = 0.04;
    const noiseFilter = ctx.createBiquadFilter();
    noiseFilter.type = 'highpass';
    noiseFilter.frequency.value = 800;
    noiseSrc.connect(noiseFilter);
    noiseFilter.connect(noiseG);
    noiseG.connect(bgmGain);
    noiseSrc.start();

    // 低音线
    const bassOsc = ctx.createOscillator();
    bassOsc.type = 'sine';
    const bassG = ctx.createGain();
    bassG.gain.value = 0.12;
    const bassFilter = ctx.createBiquadFilter();
    bassFilter.type = 'lowpass';
    bassFilter.frequency.value = 300;
    bassOsc.connect(bassFilter);
    bassFilter.connect(bassG);
    bassG.connect(bgmGain);
    bassOsc.start();

    // 和弦 oscillator 组
    const chordOscs = [];
    const chordGains = [];

    let chordIdx = 0;
    const chordDuration = 3.2; // 每和弦约3.2秒 (60BPM下约3拍)

    function playChord() {
      if (!bgmActive) return;
      // 清理旧 oscillator
      chordOscs.forEach(o => { try { o.stop(); } catch(e){} });
      chordOscs.length = 0;
      chordGains.length = 0;

      const chord = chords[chordIdx % chords.length];
      const now = ctx.currentTime;
      const allFreqs = [chord.root, ...chord.thirds];

      allFreqs.forEach((f, i) => {
        const osc = ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = f;
        // 微微失谐，模拟真实乐器
        osc.detune.value = (Math.random() - 0.5) * 10;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.0, now);
        g.gain.linearRampToValueAtTime(0.06, now + 0.3);
        g.gain.exponentialRampToValueAtTime(0.001, now + chordDuration);
        osc.connect(g);
        g.connect(bgmGain);
        osc.start(now);
        osc.stop(now + chordDuration + 0.1);
        chordOscs.push(osc);
        chordGains.push(g);
      });

      // 低音跟随根音
      bassOsc.frequency.setValueAtTime(chord.root / 2, now); // 低八度
      bassOsc.frequency.linearRampToValueAtTime(chord.root / 2 * 1.01, now + chordDuration);

      chordIdx++;
      if (bgmActive) bgmTimeout = setTimeout(playChord, chordDuration * 1000);
    }

    playChord();

    return {
      stop: () => {
        clearTimeout(bgmTimeout);
        chordOscs.forEach(o => { try { o.stop(); } catch(e){} });
        try { bassOsc.stop(); } catch(e){}
        try { noiseSrc.stop(); } catch(e){}
      },
    };
  }

  // ── BGM 控制 ──────────────────────────────────

  let _bgmHandle = null;

  function startBGM(style) {
    if (bgmActive) stopBGM();
    _ensureCtx();
    currentStyle = style || currentStyle;
    bgmActive = true;

    const s = currentStyle;
    switch (s) {
      case 'ambient': _bgmHandle = _bgmAmbient(); break;
      case 'piano':   _bgmHandle = _bgmPiano(); break;
      case '8bit':    _bgmHandle = _bgm8bit(); break;
      case 'lofi':    _bgmHandle = _bgmLofi(); break;
      default:        _bgmHandle = _bgmPiano(); break;
    }

    // 环境音循环（8秒后重新触发）
    if (s === 'ambient') {
      const loop = () => {
        if (!bgmActive || currentStyle !== 'ambient') return;
        if (_bgmHandle && _bgmHandle.oscillators) {
          _bgmHandle.oscillators.forEach(o => { try { o.stop(); } catch(e){} });
        }
        _bgmHandle = _bgmAmbient();
        bgmTimeout = setTimeout(loop, 8000);
      };
      bgmTimeout = setTimeout(loop, 8000);
    }
  }

  function stopBGM() {
    bgmActive = false;
    if (bgmTimeout) { clearTimeout(bgmTimeout); bgmTimeout = null; }
    if (_bgmHandle) {
      if (_bgmHandle.stop) _bgmHandle.stop();
      if (_bgmHandle.oscillators) {
        _bgmHandle.oscillators.forEach(o => { try { o.stop(); } catch(e){} });
      }
      _bgmHandle = null;
    }
  }

  function setBGMVolume(v) {
    bgmVolume = Math.max(0, Math.min(1, v));
    if (bgmGain) bgmGain.gain.value = bgmVolume;
    try { localStorage.setItem('cc-bgm-volume', bgmVolume); } catch(e){}
  }

  function getBGMVolume() { return bgmVolume; }

  function setSFXVolume(v) {
    sfxVolume = Math.max(0, Math.min(1, v));
    if (sfxGain) sfxGain.gain.value = sfxVolume;
    try { localStorage.setItem('cc-sfx-volume', sfxVolume); } catch(e){}
  }

  function getSFXVolume() { return sfxVolume; }

  function isBGMPlaying() { return bgmActive; }

  // ── 初始化（恢复音量设置） ─────────────────────

  function init() {
    if (_initialized) return;
    _initialized = true;
    try {
      const bv = localStorage.getItem('cc-bgm-volume');
      if (bv !== null) bgmVolume = parseFloat(bv);
      const sv = localStorage.getItem('cc-sfx-volume');
      if (sv !== null) sfxVolume = parseFloat(sv);
      const bs = localStorage.getItem('cc-bgm-style');
      if (bs && ['ambient','piano','8bit','lofi'].includes(bs)) currentStyle = bs;
    } catch(e){}
    // 在首次用户交互时激活 AudioContext
    const resume = () => {
      _ensureCtx();
      document.removeEventListener('click', resume);
      document.removeEventListener('keydown', resume);
    };
    document.addEventListener('click', resume);
    document.addEventListener('keydown', resume);
  }

  // ── 公共 API ──────────────────────────────────

  return {
    init, playSelect, playMove, playJump, playVictory,
    playUndo, playClick, playInvalid,
    startBGM, stopBGM, isBGMPlaying,
    setBGMVolume, getBGMVolume,
    setSFXVolume, getSFXVolume,
    getBgmStyle() { return currentStyle; },
    setBgmStyle(s) {
      if (!['ambient','piano','8bit','lofi'].includes(s)) return;
      currentStyle = s;
      try { localStorage.setItem('cc-bgm-style', s); } catch(e){}
      if (bgmActive) { stopBGM(); startBGM(s); }
    },
    // 兼容旧接口：切换主题时不再联动 BGM
    setTheme(t) { /* no-op: BGM 已与主题解耦 */ },
  };
})();
