document.addEventListener('DOMContentLoaded', () => {

    class Chord {
        static NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
        static NOTES_FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];

        // 各コードタイプの構成音（ルートからの半音差）
        static INTERVALS = {
            '': [0, 4, 7],         // Major
            'M7': [0, 4, 7, 11],    // Major 7th
            '7': [0, 4, 7, 10],     // Dominant 7th
            'm': [0, 3, 7],         // Minor
            'm7': [0, 3, 7, 10],    // Minor 7th
            'mM7': [0, 3, 7, 11],   // Minor Major 7th
            'm7b5': [0, 3, 6, 10],  // Half-Diminished
            'dim': [0, 3, 6],       // Diminished
            'dim7': [0, 3, 6, 9],   // Diminished 7th
            'aug': [0, 4, 8],       // Augmented
            'sus4': [0, 5, 7]       // Suspended 4th
        };

        static midiToNoteName(midi, useFlats = false) {
            const notes = useFlats ? this.NOTES_FLAT : this.NOTES;
            const octave = Math.floor(midi / 12) - 1;
            const noteIndex = midi % 12;
            return notes[noteIndex] + octave;
        }

        static getVoicing(chordName) {
            let rootStr, quality;
            if (chordName.length > 1 && (chordName[1] === '#' || chordName[1] === 'b')) {
                rootStr = chordName.substring(0, 2);
                quality = chordName.substring(2);
            } else {
                rootStr = chordName.substring(0, 1);
                quality = chordName.substring(1);
            }

            if (quality === 'M7') quality = 'M7';
            else if(quality.startsWith('m')) {}
            else {
                if (this.INTERVALS[quality] === undefined && this.INTERVALS[quality.toLowerCase()]){
                    quality = quality.toLowerCase();
                } else if (this.INTERVALS[quality] === undefined && chordName.length <=2) {
                    quality = "";
                }
            }

            const useFlats = rootStr.includes('b');
            const notes = useFlats ? this.NOTES_FLAT : this.NOTES;
            let rootMidi = notes.indexOf(rootStr);
            if (rootMidi === -1) return [];
            rootMidi += 48;

            const intervals = this.INTERVALS[quality];
            if (!intervals) return [];

            return intervals.map(interval => {
                const noteMidi = rootMidi + interval;
                return this.midiToNoteName(noteMidi, useFlats);
            });
        }
    }

    // --- DOM Elements ---
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

    // --- Audio Synthesis ---
    const leadSynth = new Tone.MonoSynth({
        // ノコギリ波(sawtooth)は、管楽器の元になる複雑な倍音を多く含んでおり加工に適しています
        oscillator: {
            type: 'sawtooth'
        },
        // 吹奏楽器のような、少し遅れて立ち上がり、長く持続する音量を表現します
        envelope: {
            attack: 0.05,   // 息を吹き込むような、わずかに遅い立ち上がり
            decay: 0.2,
            sustain: 0.7,   // キーを押している間は音量を高く保つ
            release: 0.15   // 息を止めるとスッと音が切れる感じ
        },
        // フィルターで高音を削り、アタック時に音が開くことで「ブワッ」というニュアンスを加えます
        filter: {
            Q: 2,
            type: 'lowpass', // 高音域をカットするフィルター
            frequency: 1200  // 音の基本的な明るさ。値を下げるとこもる
        },
        filterEnvelope: {
            attack: 0.06,
            decay: 0.1,
            sustain: 0.5,
            release: 0.2,
            baseFrequency: 300, // フィルターの基本位置（暗め）
            octaves: 3.5        // アタック時にフィルターが動く幅。サックスの表情をつけます
        }
    }).toDestination();

    const pianoSynth = new Tone.PolySynth(Tone.Synth, {
        oscillator: { type: 'triangle' },
        envelope: { attack: 0.01, decay: 0.5, sustain: 0.2, release: 1 },
    }).toDestination();
    pianoSynth.volume.value = -12;

    // --- Musical Constants ---
    const BEATS_PER_MEASURE = 4;
    const TICKS_PER_BEAT = Tone.Transport.PPQ;
    const TICKS_PER_MEASURE = TICKS_PER_BEAT * BEATS_PER_MEASURE;

    // --- State Management ---
    let chordMelodies = {};
    let progression = [];
    let activeChord = null;
    let currentNoteIndex = 0;
    let isPlaying = false;
    let animationFrameId = null;
    let activeLeadNoteInfo = null;
    let midiKeyDownCount = 0;
    let spacebarActive = false;
    let backingPart = null;

    // --- Initial Setup & Event Listeners ---
    setupMidi();
    setupKeyboardListener();

    if (bpmSlider) {
        bpmSlider.addEventListener('input', (e) => {
            const newBpm = e.target.value;
            bpmValue.textContent = newBpm;
            Tone.Transport.bpm.value = newBpm;
        });
    }
    if (generateButton) {
        generateButton.addEventListener('click', generatePhrases);
    }
    if (playStopButton) {
        playStopButton.addEventListener('click', togglePlayback);
    }

    // --- Core Functions ---

    async function generatePhrases() {
        generateButton.disabled = true;
        playStopButton.disabled = true;
        generateButton.textContent = 'フレーズ生成中...';
        statusArea.textContent = 'AIがメロディを考えています...';
        stopPlayback();
        pianoRollContent.innerHTML = '';
        pianoRollContent.appendChild(playhead);

        try {
            const requestBody = {
                chord_progression: chordSelect.value,
                style: styleSelect.value,
            };
            const response = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP Error: ${response.status} - ${errorText}`);
            }

            const data = await response.json();
            progression = Object.keys(data.chord_melodies);
            chordMelodies = {};

            for (const chord in data.chord_melodies) {
                const decoded = atob(data.chord_melodies[chord]);
                let accumulatedWait = 0;
                chordMelodies[chord] = decoded.trim().split('\n').map(line => {
                    const [pitch, duration, wait, velocity] = line.split(' ').map(Number);
                    const startTime = accumulatedWait;
                    accumulatedWait += wait;
                    return { pitch, duration, wait, velocity, startTime };
                }).filter(note => !isNaN(note.pitch));
            }

            updateProgressionDisplay();
            drawTimingIndicators();
            playStopButton.disabled = false;
            statusArea.textContent = 'フレーズ生成完了。「演奏開始」ボタンを押してください。';

        } catch (error) {
            console.error('フレーズ生成に失敗:', error.message);
            statusArea.textContent = `エラー: ${error.message}`;
        } finally {
            generateButton.disabled = false;
            generateButton.textContent = '1. フレーズをAIに生成させる';
        }
    }

    async function togglePlayback() {
        if (progression.length === 0) return;
        await ensureAudioContext();
        if (isPlaying) {
            stopPlayback();
        } else {
            startPlayback();
        }
        if (playStopButton) playStopButton.blur();
    }

    function startPlayback() {
        const playedNotes = pianoRollContent.querySelectorAll('.note-block');
        playedNotes.forEach(note => note.remove());
        scheduleBackingTrack();
        Tone.Transport.seconds = 0;
        Tone.Transport.start();
        isPlaying = true;
        playStopButton.textContent = '演奏停止';
        playStopButton.classList.replace('bg-green-600', 'bg-red-600');
        playStopButton.classList.replace('hover:bg-green-700', 'hover:bg-red-700');
        animatePlayhead();
    }

    function stopPlayback() {
        Tone.Transport.stop();
        Tone.Transport.cancel(0);
        if (backingPart) {
            backingPart.stop(0).clear().dispose();
            backingPart = null;
        }
        
        // BUGFIX: MonoSynthにはreleaseAllがないため、triggerReleaseに変更
        if (leadSynth) leadSynth.triggerRelease();
        if (pianoSynth) pianoSynth.releaseAll();
        
        activeLeadNoteInfo = null;
        midiKeyDownCount = 0;
        spacebarActive = false;

        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        playhead.style.left = '0%';
        document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-yellow-400'));
        activeChord = null;
        isPlaying = false;
        playStopButton.textContent = '2. 演奏開始';
        playStopButton.classList.replace('bg-red-600', 'bg-green-600');
        playStopButton.classList.replace('hover:bg-red-700', 'hover:bg-green-700');
        noteDisplayArea.textContent = '...';
    }

    function scheduleBackingTrack() {
        if (backingPart) {
            backingPart.stop(0).clear().dispose();
            backingPart = null;
        }

        const events = [];
        progression.forEach((chord, measureIndex) => {
            const chordName = chord.split('_')[0];
            const notes = Chord.getVoicing(chordName);

            events.push({
                time: Tone.Ticks(measureIndex * TICKS_PER_MEASURE).toSeconds(),
                type: 'update',
                chord: progression[measureIndex],
                chordIndex: measureIndex
            });

            if (notes.length > 0) {
                for (let beat = 0; beat < BEATS_PER_MEASURE; beat++) {
                    const startTimeInTicks = (measureIndex * TICKS_PER_MEASURE) + (beat * TICKS_PER_BEAT);
                    events.push({
                        time: Tone.Ticks(startTimeInTicks).toSeconds(),
                        type: 'play',
                        notes: [...notes],
                        duration: '4n'
                    });
                }
            }
        });

        if (events.length === 0) return;

        backingPart = new Tone.Part((time, value) => {
            if (value.type === 'play') {
                pianoSynth.triggerAttackRelease(value.notes, value.duration, time);
            } else if (value.type === 'update') {
                Tone.Draw.schedule(() => {
                    activeChord = value.chord;
                    currentNoteIndex = 0;
                    updateNoteDisplay(chordMelodies[activeChord]);
                    document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-yellow-400'));
                    const activeIndicator = document.getElementById(`indicator-${value.chordIndex}`);
                    if (activeIndicator) activeIndicator.classList.add('bg-yellow-400');
                }, time);
            }
        }, events).start(0);

        backingPart.loop = true;
        const totalTicks = progression.length * TICKS_PER_MEASURE;
        backingPart.loopEnd = Tone.Ticks(totalTicks).toSeconds();
    }

    async function playNextLeadNote(velocity = 0.75) {
        await ensureAudioContext();
        if (!isPlaying || !activeChord || !chordMelodies[activeChord] || chordMelodies[activeChord].length === 0) {
            return;
        }
        if (activeLeadNoteInfo) {
            return;
        }

        const notesOfCurrentChord = chordMelodies[activeChord];
        const noteToPlay = notesOfCurrentChord[currentNoteIndex];
        if (!noteToPlay) return;

        const pitch = noteToPlay.pitch;
        if (typeof pitch !== 'number') return;

        const freq = Tone.Midi(pitch).toFrequency();
        leadSynth.triggerAttack(freq, Tone.now(), velocity);

        const noteStartTicks = Tone.Transport.ticks;
        const noteElement = drawPlayedNote(pitch, noteStartTicks);

        activeLeadNoteInfo = {
            pitch: pitch,
            startTicks: noteStartTicks,
            element: noteElement
        };

        currentNoteIndex = (currentNoteIndex + 1) % notesOfCurrentChord.length;
    }

    function stopCurrentLeadNote() {
        if (!activeLeadNoteInfo) return;

        const noteInfo = activeLeadNoteInfo;
        leadSynth.triggerRelease(Tone.now());

        const endTicks = Tone.Transport.ticks;
        const durationTicks = endTicks - noteInfo.startTicks;
        const totalTicks = progression.length * TICKS_PER_MEASURE;

        if (totalTicks > 0) {
            const widthPercentage = (durationTicks / totalTicks) * 100;
            if (noteInfo.element) {
                noteInfo.element.style.width = `${Math.max(0.5, widthPercentage)}%`;
            }
        }
        activeLeadNoteInfo = null;
    }

    function drawPlayedNote(pitch, startTicks) {
        const PITCH_MIN = 48, PITCH_MAX = 84, PITCH_RANGE = PITCH_MAX - PITCH_MIN;
        if (pitch < PITCH_MIN || pitch > PITCH_MAX) return null;
        
        const noteBlock = document.createElement('div');
        noteBlock.className = 'note-block';
        
        const totalTicks = progression.length * TICKS_PER_MEASURE;
        if (totalTicks === 0) return null;
        
        const currentLoopTicks = startTicks % totalTicks;
        const leftPercentage = (currentLoopTicks / totalTicks) * 100;
        const topPercentage = 100 - ((pitch - PITCH_MIN) / PITCH_RANGE) * 100;
        
        noteBlock.style.top = `${topPercentage}%`;
        noteBlock.style.height = `${100 / PITCH_RANGE}%`;
        noteBlock.style.left = `${leftPercentage}%`;
        noteBlock.style.width = `1%`;
        
        pianoRollContent.appendChild(noteBlock);
        return noteBlock;
    }

    function drawTimingIndicators() {
        const indicators = pianoRollContent.querySelectorAll('.timing-indicator');
        indicators.forEach(ind => ind.remove());

        const totalMeasures = progression.length;
        const totalTicks = totalMeasures * TICKS_PER_MEASURE;
        if (totalTicks === 0) return;

        progression.forEach((chordKey, measureIndex) => {
            const notes = chordMelodies[chordKey];
            if (!notes) return;
            notes.forEach(note => {
                const indicator = document.createElement('div');
                indicator.className = 'timing-indicator';
                const noteStartTick = measureIndex * TICKS_PER_MEASURE + note.startTime;
                const leftPercentage = (noteStartTick / totalTicks) * 100;
                indicator.style.left = `${leftPercentage}%`;
                pianoRollContent.appendChild(indicator);
            });
        });
    }

    function updateProgressionDisplay() {
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

    function updateNoteDisplay(notes) {
        if (!noteDisplayArea || !notes || notes.length === 0) {
            if (noteDisplayArea) noteDisplayArea.textContent = '...';
            return;
        }
        const pitchList = notes.map(n => n.pitch).join(' ');
        noteDisplayArea.textContent = pitchList;
    }

    function animatePlayhead() {
        if (!isPlaying) {
            animationFrameId = null;
            return;
        }
        const totalMeasures = progression.length;
        if (totalMeasures === 0) {
            animationFrameId = requestAnimationFrame(animatePlayhead);
            return;
        }
        const totalTicks = totalMeasures * TICKS_PER_MEASURE;
        const currentLoopTicks = Tone.Transport.ticks % totalTicks;
        const progress = currentLoopTicks / totalTicks;
        playhead.style.left = `${progress * 100}%`;
        animationFrameId = requestAnimationFrame(animatePlayhead);
    }

    function setupKeyboardListener() {
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
            if (e.code === 'Space') {
                e.preventDefault();
                if (!e.repeat && !spacebarActive) {
                    spacebarActive = true;
                    playNextLeadNote();
                }
            }
        });
        document.addEventListener('keyup', (e) => {
            if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
            if (e.code === 'Space' && spacebarActive) {
                spacebarActive = false;
                stopCurrentLeadNote();
            }
        });
    }
    
    function handleMidiNoteOn(velocity = 0.75) {
        midiKeyDownCount++;
        if (midiKeyDownCount === 1) {
            playNextLeadNote(velocity);
        }
    }

    function handleMidiNoteOff() {
        if (midiKeyDownCount > 0) {
            midiKeyDownCount--;
        }
        if (midiKeyDownCount === 0) {
            stopCurrentLeadNote();
        }
    }

    async function setupMidi() {
        if (!navigator.requestMIDIAccess) return;
        try {
            if (typeof WebMidi === 'undefined') return;
            await WebMidi.enable();
            const midiInput = WebMidi.inputs[0];
            if (midiInput) {
                statusArea.textContent = `MIDI In: ${midiInput.name}`;
                midiInput.on("noteon", e => handleMidiNoteOn(e.velocity));
                midiInput.on("noteoff", e => handleMidiNoteOff());
            } else {
                statusArea.textContent = 'MIDIデバイス未接続。PCキーボードのスペースキーで演奏できます。';
            }
        } catch (err) {
            console.error("Could not enable MIDI:", err);
            statusArea.textContent = 'MIDIデバイスの有効化に失敗しました。';
        }
    }

    async function ensureAudioContext() {
        if (Tone.context.state !== 'running') {
            await Tone.start();
        }
    }
});
