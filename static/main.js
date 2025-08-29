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
    const pianoRollContainer = document.getElementById('piano-roll-container');
    const playhead = document.getElementById('playhead');
    // 【追加】音程表示用のDOM要素
    const noteDisplayArea = document.getElementById('note-display-area');
    const currentPitchDisplay = document.getElementById('current-pitch-display');

    // --- 音楽関連 ---
    const synth = new Tone.PolySynth(Tone.Synth).toDestination();

    // --- 状態管理 ---
    let chordMelodies = {};
    let progression = [];
    let activeChord = null;
    let currentNoteIndex = 0;
    let isPlaying = false;
    let animationFrameId = null;

    // --- 初期化 ---
    setupMidi();
    setupKeyboardListener();

    // --- イベントリスナー (変更なし) ---
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

    async function ensureAudioContext() {
        if (Tone.context.state !== 'running') {
            await Tone.start();
        }
    }

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
            let totalWaitTime = 0;
            for (const chord in data.chord_melodies) {
                const decoded = atob(data.chord_melodies[chord]);
                let accumulatedWait = 0;
                chordMelodies[chord] = decoded.trim().split('\n')
                    .map(line => {
                        const [pitch, duration, wait, velocity] = line.split(' ').map(Number);
                        const startTime = accumulatedWait;
                        accumulatedWait += wait;
                        return { pitch, duration, wait, velocity, startTime };
                    })
                    .filter(note => !isNaN(note.pitch));
                totalWaitTime = Math.max(totalWaitTime, accumulatedWait);
            }
            pianoRollContainer.dataset.totalWaitTime = totalWaitTime > 0 ? totalWaitTime : 128;

            updateProgressionDisplay();
            if (progression.length > 0) {
                const firstChord = progression[0];
                drawPianoRoll(chordMelodies[firstChord]);
                // 【追加】最初のフレーズをテキスト表示
                updateNoteDisplay(chordMelodies[firstChord]);
            }
            statusArea.textContent = 'フレーズ生成完了。「演奏開始」ボタンを押してください。';

        } catch (error) {
            console.error('フレーズ生成に失敗:', error);
            statusArea.textContent = `エラー: ${error.message}`;
        } finally {
            generateButton.disabled = false;
            generateButton.textContent = '1. フレーズをAIに生成させる';
        }
    }

    function togglePlayback() {
        if (progression.length === 0) {
            statusArea.textContent = '先にフレーズを生成してください。';
            return;
        }
        ensureAudioContext();
        if (isPlaying) {
            stopPlayback();
        } else {
            startPlayback();
        }
    }

    function startPlayback() {
        Tone.Transport.start();
        isPlaying = true;
        if (playStopButton) {
            playStopButton.textContent = '演奏停止';
            playStopButton.classList.replace('bg-green-600', 'bg-red-600');
            playStopButton.classList.replace('hover:bg-green-700', 'hover:bg-red-700');
        }
        animatePlayhead();
    }

    function stopPlayback() {
        Tone.Transport.stop();
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        if(playhead) playhead.style.left = '0%';

        document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-yellow-400'));
        activeChord = null;
        isPlaying = false;
        if (playStopButton) {
            playStopButton.textContent = '2. 演奏開始';
            playStopButton.classList.replace('bg-red-600', 'bg-green-600');
            playStopButton.classList.replace('hover:bg-red-700', 'hover:bg-green-700');
        }
        // 【追加】表示をリセット
        if (noteDisplayArea) noteDisplayArea.textContent = '...';
        if (currentPitchDisplay) currentPitchDisplay.textContent = '--';
    }

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

    Tone.Transport.scheduleRepeat((time) => {
        const currentMeasure = Math.floor(Tone.Transport.position.split(':')[0]);
        const chordIndex = currentMeasure % progression.length;
        const newActiveChord = progression[chordIndex];

        if (activeChord !== newActiveChord) {
            activeChord = newActiveChord;
            currentNoteIndex = 0;
            Tone.Draw.schedule(() => {
                const notes = chordMelodies[activeChord];
                drawPianoRoll(notes);
                // 【追加】フレーズテキストを更新
                updateNoteDisplay(notes);
            }, time);
        }
        
        Tone.Draw.schedule(() => {
            document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-yellow-400'));
            const activeIndicator = document.getElementById(`indicator-${chordIndex}`);
            if (activeIndicator) activeIndicator.classList.add('bg-yellow-400');
        }, time);
    }, "1m");


    async function playNextNote(velocity = 0.75) {
        await ensureAudioContext();
        if (!isPlaying || !activeChord || !chordMelodies[activeChord] || chordMelodies[activeChord].length === 0) return;
        const notesOfCurrentChord = chordMelodies[activeChord];
        const noteToPlay = notesOfCurrentChord[currentNoteIndex];
        if (!noteToPlay || typeof noteToPlay.pitch !== 'number' || isNaN(noteToPlay.pitch)) {
            currentNoteIndex = (currentNoteIndex + 1) % notesOfCurrentChord.length;
            return;
        }
        const freq = Tone.Midi(noteToPlay.pitch).toFrequency();
        synth.triggerAttackRelease(freq, "8n", Tone.now(), velocity);
        
        // 【追加】発音した音程を表示
        if (currentPitchDisplay) {
            currentPitchDisplay.textContent = noteToPlay.pitch;
            // アニメーション効果
            currentPitchDisplay.classList.remove('scale-125');
            void currentPitchDisplay.offsetWidth; // Reflow to restart animation
            currentPitchDisplay.classList.add('scale-125');

        }

        currentNoteIndex = (currentNoteIndex + 1) % notesOfCurrentChord.length;
    }
    
    // --- 【ここから新規・変更箇所】 ---
    
    /**
     * 【追加】フレーズの音程リストをテキスト表示エリアに更新する
     * @param {Array} notes - 表示するノートの配列
     */
    function updateNoteDisplay(notes) {
        if (!noteDisplayArea || !notes) {
            if (noteDisplayArea) noteDisplayArea.textContent = '';
            return;
        }
        const pitchList = notes.map(n => n.pitch).join(' ');
        noteDisplayArea.textContent = pitchList;
    }

    function drawPianoRoll(notes) {
        if (!pianoRollContainer || !notes) return;
        while (pianoRollContainer.firstChild && pianoRollContainer.firstChild !== playhead && pianoRollContainer.firstChild !== currentPitchDisplay) {
            pianoRollContainer.removeChild(pianoRollContainer.firstChild);
        }
        const PITCH_MIN = 48;
        const PITCH_MAX = 84;
        const PITCH_RANGE = PITCH_MAX - PITCH_MIN;
        const totalWaitTime = parseFloat(pianoRollContainer.dataset.totalWaitTime) || 128;

        notes.forEach(note => {
            if (note.pitch < PITCH_MIN || note.pitch > PITCH_MAX) return;
            const noteBlock = document.createElement('div');
            noteBlock.className = 'note-block';
            const topPercentage = 100 - ((note.pitch - PITCH_MIN) / PITCH_RANGE) * 100;
            noteBlock.style.top = `${topPercentage}%`;
            noteBlock.style.height = `${100 / PITCH_RANGE}%`;
            const leftPercentage = (note.startTime / totalWaitTime) * 100;
            const widthPercentage = (note.duration / totalWaitTime) * 100;
            noteBlock.style.left = `${leftPercentage}%`;
            noteBlock.style.width = `${widthPercentage}%`;
            
            pianoRollContainer.insertBefore(noteBlock, playhead);
        });
    }

    function animatePlayhead() {
        if (!isPlaying || !playhead) {
            animationFrameId = null;
            return;
        }
        const progress = Tone.Transport.progress;
        playhead.style.left = `${progress * 100}%`;
        animationFrameId = requestAnimationFrame(animatePlayhead);
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


