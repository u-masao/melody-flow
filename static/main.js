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

    // --- 音楽関連 ---
    const synth = new Tone.PolySynth(Tone.Synth).toDestination();

    // --- 状態管理 ---
    let chordMelodies = {};
    let progression = [];
    let activeChord = null;
    let currentNoteIndex = 0;
    let isPlaying = false;

    // --- 初期化 ---
    setupMidi();
    setupKeyboardListener();
    
    // --- イベントリスナー ---
    if (bpmSlider) {
        bpmSlider.addEventListener('input', (e) => {
            const newBpm = e.target.value;
            if (bpmValue) bpmValue.textContent = newBpm;
            Tone.Transport.bpm.value = newBpm;
        });
    }

    if (generateButton) {
        generateButton.addEventListener('click', generatePhrases);
    }

    if (playStopButton) {
        playStopButton.addEventListener('click', togglePlayback);
    }

    // --- 機能関数 ---

    /**
     * AudioContextが 'running' 状態でない場合のみTone.start()を呼び出す関数
     */
    async function ensureAudioContext() {
        if (Tone.context.state !== 'running') {
            await Tone.start();
        }
    }

    /** AIにフレーズを生成させる */
    async function generatePhrases() {
        if (!generateButton) return;
        generateButton.disabled = true;
        generateButton.textContent = 'AIが作曲中...';
        statusArea.textContent = 'コードごとにフレーズを生成しています...';
        stopPlayback();

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chord_progression: chordSelect.value,
                    style: styleSelect.value,
                }),
            });
            if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
            
            const data = await response.json();
            progression = Object.keys(data.chord_melodies);

            chordMelodies = {};
            for (const chord in data.chord_melodies) {
                const decoded = atob(data.chord_melodies[chord]);
                chordMelodies[chord] = decoded.trim().split('\n')
                    .map(line => {
                        const [pitch, duration, wait, velocity] = line.split(' ').map(Number);
                        return { pitch, duration, wait, velocity };
                    })
                    .filter(note => !isNaN(note.pitch));
            }

            updateProgressionDisplay();
            statusArea.textContent = 'フレーズ生成完了。「演奏開始」ボタンを押してください。';

        } catch (error) {
            console.error('フレーズ生成に失敗:', error);
            statusArea.textContent = `エラー: ${error.message}`;
        } finally {
            generateButton.disabled = false;
            generateButton.textContent = '1. フレーズをAIに生成させる';
        }
    }

    /** 演奏の開始/停止をトグルする */
    async function togglePlayback() {
        if (progression.length === 0) {
            statusArea.textContent = '先にフレーズを生成してください。';
            return;
        }
        await ensureAudioContext();
        if (isPlaying) {
            stopPlayback();
        } else {
            startPlayback();
        }
    }

    /** 演奏を開始する */
    function startPlayback() {
        Tone.Transport.start();
        isPlaying = true;
        if (playStopButton) {
            playStopButton.textContent = '演奏停止';
            playStopButton.classList.replace('bg-green-600', 'bg-red-600');
            playStopButton.classList.replace('hover:bg-green-700', 'hover:bg-red-700');
        }
    }

    /** 演奏を停止する */
    function stopPlayback() {
        Tone.Transport.stop();
        document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-yellow-400'));
        activeChord = null;
        isPlaying = false;
        if (playStopButton) {
            playStopButton.textContent = '2. 演奏開始';
            playStopButton.classList.replace('bg-red-600', 'bg-green-600');
            playStopButton.classList.replace('hover:bg-red-700', 'hover:bg-green-700');
        }
    }

    /** 進行表示UIを更新する */
    function updateProgressionDisplay() {
        if (!progressionDisplay) return;
        progressionDisplay.innerHTML = '';
        progression.forEach((chord, index) => {
            const chordName = chord.split('_')[0];
            const el = document.createElement('div');
            el.id = `indicator-${index}`;
            el.className = 'indicator text-center p-2 rounded-md w-20';
            el.textContent = chordName;
            progressionDisplay.appendChild(el);
        });
    }

    // 1小節ごとに実行されるイベント
    Tone.Transport.scheduleRepeat((time) => {
        const currentMeasure = Math.floor(Tone.Transport.position.split(':')[0]);
        const chordIndex = currentMeasure % progression.length;
        
        Tone.Draw.schedule(() => {
            document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-yellow-400'));
            const activeIndicator = document.getElementById(`indicator-${chordIndex}`);
            if (activeIndicator) {
                activeIndicator.classList.add('bg-yellow-400');
            }
        }, time);

        activeChord = progression[chordIndex];
        currentNoteIndex = 0;
    }, "1m");

    /** 次のノートを再生する */
    async function playNextNote(velocity = 0.75) {
        await ensureAudioContext();
        
        if (!isPlaying || !activeChord || !chordMelodies[activeChord] || chordMelodies[activeChord].length === 0) {
            return;
        }

        const notesOfCurrentChord = chordMelodies[activeChord];
        const noteToPlay = notesOfCurrentChord[currentNoteIndex];
        
        if (!noteToPlay || typeof noteToPlay.pitch !== 'number' || isNaN(noteToPlay.pitch)) {
            currentNoteIndex = (currentNoteIndex + 1) % notesOfCurrentChord.length;
            return;
        }
        
        const freq = Tone.Midi(noteToPlay.pitch).toFrequency();
        synth.triggerAttackRelease(freq, "8n", Tone.now(), velocity);

        currentNoteIndex = (currentNoteIndex + 1) % notesOfCurrentChord.length;
    }
    
    function setupKeyboardListener() {
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && !e.repeat) playNextNote();
        });
    }
    async function setupMidi() {
        if (!navigator.requestMIDIAccess) return;
        try {
            await WebMidi.enable();
            const midiInput = WebMidi.inputs[0];
            if (midiInput && statusArea) {
                statusArea.textContent = `接続中: ${midiInput.name}`;
                midiInput.channels[1].addListener("noteon", e => playNextNote(e.velocity));
            }
        } catch (err) {
            console.warn("MIDIの初期化に失敗:", err);
        }
    }
});

