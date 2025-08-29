document.addEventListener('DOMContentLoaded', () => {
    // --- DOM要素 ---
    const chordSelect = document.getElementById('chord-progression');
    const styleSelect = document.getElementById('music-style');
    const generateButton = document.getElementById('generate-button');
    const bpmSlider = document.getElementById('bpm-slider');
    const bpmValue = document.getElementById('bpm-value');
    const playStopButton = document.getElementById('play-stop-button');
    const progressionDisplay = document.getElementById('progression-display');
    const statusArea = document.getElementById('status-area');
    const pianoRollContent = document.getElementById('piano-roll-content');
    const playhead = document.getElementById('playhead');
    const noteDisplayArea = document.getElementById('note-display-area');

    // --- 音楽関連 ---
    // シンセサイザーをletで宣言し、再生成できるようにする
    let leadSynth = new Tone.PolySynth(Tone.Synth).toDestination();
    
    // 【変更】バッキング用のシンセをピアノに変更
    let pianoSynth = new Tone.PolySynth(Tone.Synth, {
        oscillator: { type: 'triangle' }, // 柔らかい音色
        envelope: { attack: 0.01, decay: 0.5, sustain: 0.2, release: 1 },
    }).toDestination();
    pianoSynth.volume.value = -12; // バッキングなので音量を下げる

    // 【変更】コードの構成音を定義
    const CHORD_VOICINGS = {
        'C': ['C3', 'E3', 'G3'],
        'G': ['B2', 'D3', 'G3'],
        'Am': ['A2', 'C3', 'E3'],
        'F': ['A2', 'C3', 'F3'],
        'Em': ['E3', 'G3', 'B3'],
        'Dm7': ['D3', 'F3', 'A3', 'C4'],
        'G7': ['G2', 'B2', 'D3', 'F3'],
        'Cmaj7': ['C3', 'E3', 'G3', 'B3'],
        'E7': ['E2', 'G#2', 'B2', 'D3'],
    };
    const BEATS_PER_MEASURE = 4;
    const TICKS_PER_MEASURE = Tone.Transport.PPQ * BEATS_PER_MEASURE;

    // --- 状態管理 ---
    let chordMelodies = {};
    let progression = [];
    let activeChord = null;
    let currentNoteIndex = 0;
    let isPlaying = false;
    let animationFrameId = null;
    let activeNotes = {};
    let spacebarActive = false;
    // 【変更】バッキングパートの変数名を変更
    let backingPart = null;

    // --- 初期化 & イベントリスナー (変更なし) ---
    setupMidi();
    setupKeyboardListener();
    if (bpmSlider) { bpmSlider.addEventListener('input', (e) => { const newBpm = e.target.value; bpmValue.textContent = newBpm; Tone.Transport.bpm.value = newBpm; }); }
    if (generateButton) { generateButton.addEventListener('click', generatePhrases); }
    if (playStopButton) { playStopButton.addEventListener('click', togglePlayback); }

    // --- 機能関数 ---
    
    // 【変更】stopPlayback関数をピアノ用に修正
    function stopPlayback() {
        Tone.Transport.stop();
        if (leadSynth) leadSynth.dispose();
        leadSynth = new Tone.PolySynth(Tone.Synth).toDestination();
        if (pianoSynth) pianoSynth.dispose();
        pianoSynth = new Tone.PolySynth(Tone.Synth, { oscillator: { type: 'triangle' }, envelope: { attack: 0.01, decay: 0.5, sustain: 0.2, release: 1 }, }).toDestination();
        pianoSynth.volume.value = -12;

        activeNotes = {};
        spacebarActive = false;
        if (animationFrameId) { cancelAnimationFrame(animationFrameId); animationFrameId = null; }
        playhead.style.left = '0%';
        document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-yellow-400'));
        activeChord = null;
        isPlaying = false;
        playStopButton.textContent = '2. 演奏開始';
        playStopButton.classList.replace('bg-red-600', 'bg-green-600');
        playStopButton.classList.replace('hover:bg-red-700', 'hover:bg-green-700');
        noteDisplayArea.textContent = '...';
    }
    
    // 【変更】バッキングトラックのスケジューリングをピアノ用に全面的に書き換え
    function scheduleBackingTrack() {
        if (backingPart) {
            backingPart.stop(0).clear().dispose();
        }
        
        const pianoEvents = progression.map((chord, i) => {
            const chordName = chord.split('_')[0];
            const notes = CHORD_VOICINGS[chordName] || [];
            // 各小節の頭で全音符のコードを鳴らす
            return { time: `${i}m`, notes: notes, duration: '1m' };
        });

        backingPart = new Tone.Part((time, value) => {
            if (value.notes.length > 0) {
                pianoSynth.triggerAttackRelease(value.notes, value.duration, time);
            }
        }, pianoEvents).start(0);

        backingPart.loop = true;
        backingPart.loopEnd = `${progression.length}m`;
    }

    // (これ以降の他の関数は、前のバージョンから変更ありません)
    async function generatePhrases() { generateButton.disabled = true; playStopButton.disabled = true; generateButton.textContent = 'フレーズ生成中...'; statusArea.textContent = 'AIがメロディを考えています...'; stopPlayback(); pianoRollContent.innerHTML = ''; pianoRollContent.appendChild(playhead); try { const requestBody = { chord_progression: chordSelect.value, style: styleSelect.value, }; const response = await fetch('/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody), }); if (!response.ok) { const errorText = await response.text(); throw new Error(`HTTP Error: ${response.status} - ${errorText}`); } const data = await response.json(); progression = Object.keys(data.chord_melodies); chordMelodies = {}; for (const chord in data.chord_melodies) { const decoded = atob(data.chord_melodies[chord]); let accumulatedWait = 0; chordMelodies[chord] = decoded.trim().split('\n').map(line => { const [pitch, duration, wait, velocity] = line.split(' ').map(Number); const startTime = accumulatedWait; accumulatedWait += wait; return { pitch, duration, wait, velocity, startTime }; }).filter(note => !isNaN(note.pitch)); } updateProgressionDisplay(); drawTimingIndicators(); scheduleBackingTrack(); playStopButton.disabled = false; statusArea.textContent = 'フレーズ生成完了。「演奏開始」ボタンを押してください。'; } catch (error) { console.error('フレーズ生成に失敗:', error.message); statusArea.textContent = `エラー: ${error.message}`; } finally { generateButton.disabled = false; generateButton.textContent = '1. フレーズをAIに生成させる'; } }
    async function togglePlayback() { if (progression.length === 0) return; await ensureAudioContext(); if (isPlaying) { stopPlayback(); } else { startPlayback(); } if (playStopButton) playStopButton.blur(); }
    function setupKeyboardListener() { document.addEventListener('keydown', (e) => { if (e.code === 'Space') { e.preventDefault(); if (!e.repeat && !spacebarActive) { spacebarActive = true; handleNoteOn(); } } }); document.addEventListener('keyup', (e) => { if (e.code === 'Space' && spacebarActive) { spacebarActive = false; const lastPlayedPitch = Object.keys(activeNotes).pop(); if (lastPlayedPitch) { handleNoteOff(parseInt(lastPlayedPitch, 10)); } } }); }
    function startPlayback() { const playedNotes = pianoRollContent.querySelectorAll('.note-block'); playedNotes.forEach(note => note.remove()); Tone.Transport.seconds = 0; Tone.Transport.start(); isPlaying = true; playStopButton.textContent = '演奏停止'; playStopButton.classList.replace('bg-green-600', 'bg-red-600'); playStopButton.classList.replace('hover:bg-green-700', 'hover:bg-red-700'); animatePlayhead(); }
    function updateProgressionDisplay() { progressionDisplay.innerHTML = ''; progression.forEach((chord, index) => { const chordName = chord.split('_')[0]; const el = document.createElement('div'); el.id = `indicator-${index}`; el.className = 'indicator text-center p-2 rounded-md w-20'; el.textContent = chordName; progressionDisplay.appendChild(el); }); }
    async function handleNoteOn(velocity = 0.75) { await ensureAudioContext(); if (!isPlaying || !activeChord || !chordMelodies[activeChord] || chordMelodies[activeChord].length === 0) return; const notesOfCurrentChord = chordMelodies[activeChord]; const noteToPlay = notesOfCurrentChord[currentNoteIndex]; const pitch = noteToPlay.pitch; if (!noteToPlay || typeof pitch !== 'number' || activeNotes[pitch]) return; const freq = Tone.Midi(pitch).toFrequency(); leadSynth.triggerAttack(freq, Tone.now(), velocity); const noteStartTicks = Tone.Transport.ticks; const noteElement = drawPlayedNote(pitch, noteStartTicks); activeNotes[pitch] = { startTicks: noteStartTicks, element: noteElement }; currentNoteIndex = (currentNoteIndex + 1) % notesOfCurrentChord.length; }
    function handleNoteOff(pitch) { const noteInfo = activeNotes[pitch]; if (!noteInfo) return; const freq = Tone.Midi(pitch).toFrequency(); leadSynth.triggerRelease(freq, Tone.now()); const endTicks = Tone.Transport.ticks; const durationTicks = endTicks - noteInfo.startTicks; const totalTicks = progression.length * TICKS_PER_MEASURE; if (totalTicks === 0) return; const widthPercentage = (durationTicks / totalTicks) * 100; if(noteInfo.element) noteInfo.element.style.width = `${widthPercentage}%`; delete activeNotes[pitch]; }
    function drawPlayedNote(pitch, startTicks) { const PITCH_MIN = 48, PITCH_MAX = 84, PITCH_RANGE = PITCH_MAX - PITCH_MIN; if (pitch < PITCH_MIN || pitch > PITCH_MAX) return null; const noteBlock = document.createElement('div'); noteBlock.className = 'note-block'; const totalTicks = progression.length * TICKS_PER_MEASURE; if (totalTicks === 0) return null; const currentLoopTicks = startTicks % totalTicks; const leftPercentage = (currentLoopTicks / totalTicks) * 100; const topPercentage = 100 - ((pitch - PITCH_MIN) / PITCH_RANGE) * 100; noteBlock.style.top = `${topPercentage}%`; noteBlock.style.height = `${100 / PITCH_RANGE}%`; noteBlock.style.left = `${leftPercentage}%`; noteBlock.style.width = `1%`; pianoRollContent.appendChild(noteBlock); return noteBlock; }
    function drawTimingIndicators() { const indicators = pianoRollContent.querySelectorAll('.timing-indicator'); indicators.forEach(ind => ind.remove()); const totalMeasures = progression.length; const totalTicks = totalMeasures * TICKS_PER_MEASURE; if (totalTicks === 0) return; progression.forEach((chordKey, measureIndex) => { const notes = chordMelodies[chordKey]; if (!notes) return; notes.forEach(note => { const indicator = document.createElement('div'); indicator.className = 'timing-indicator'; const noteStartTick = measureIndex * TICKS_PER_MEASURE + note.startTime; const leftPercentage = (noteStartTick / totalTicks) * 100; indicator.style.left = `${leftPercentage}%`; pianoRollContent.appendChild(indicator); }); }); }
    function updateNoteDisplay(notes) { if (!noteDisplayArea || !notes) { noteDisplayArea.textContent = '...'; return; } const pitchList = notes.map(n => n.pitch).join(' '); noteDisplayArea.textContent = pitchList; }
    function animatePlayhead() { if (!isPlaying) { animationFrameId = null; return; } const totalMeasures = progression.length; if (totalMeasures === 0) { animationFrameId = requestAnimationFrame(animatePlayhead); return; } const totalTicks = totalMeasures * TICKS_PER_MEASURE; const currentLoopTicks = Tone.Transport.ticks % totalTicks; const progress = currentLoopTicks / totalTicks; playhead.style.left = `${progress * 100}%`; animationFrameId = requestAnimationFrame(animatePlayhead); }
    async function setupMidi() { if (!navigator.requestMIDIAccess) return; try { await WebMidi.enable(); const midiInput = WebMidi.inputs[0]; if (midiInput) { statusArea.textContent = `接続中: ${midiInput.name}`; midiInput.on("noteon", e => handleNoteOn(e.velocity)); midiInput.on("noteoff", e => handleNoteOff(e.note.number)); } } catch (err) { console.error("Could not enable MIDI:", err); } }
    Tone.Transport.scheduleRepeat((time) => { const totalMeasures = progression.length; if (totalMeasures === 0) return; const currentMeasure = Math.floor(Tone.Transport.position.split(':')[0]); const chordIndex = currentMeasure % totalMeasures; const newActiveChord = progression[chordIndex]; if (activeChord !== newActiveChord) { activeChord = newActiveChord; currentNoteIndex = 0; updateNoteDisplay(chordMelodies[activeChord]); } Tone.Draw.schedule(() => { document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-yellow-400')); const activeIndicator = document.getElementById(`indicator-${chordIndex}`); if (activeIndicator) activeIndicator.classList.add('bg-yellow-400'); }, time); }, "1m");
    async function ensureAudioContext() { if (Tone.context.state !== 'running') await Tone.start(); }
});

