document.addEventListener('DOMContentLoaded', () => {

    class Chord {
        static NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
        static NOTES_FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];

        static INTERVALS = {
            '': [0, 4, 7], 'M7': [0, 4, 7, 11], '7': [0, 4, 7, 10], 'm': [0, 3, 7],
            'm7': [0, 3, 7, 10], 'mM7': [0, 3, 7, 11], 'm7b5': [0, 3, 6, 10],
            'dim': [0, 3, 6], 'dim7': [0, 3, 6, 9], 'aug': [0, 4, 8], 'sus4': [0, 5, 7]
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
                rootStr = chordName.substring(0, 2); quality = chordName.substring(2);
            } else {
                rootStr = chordName.substring(0, 1); quality = chordName.substring(1);
            }
            if (quality === 'M7') {} else if (quality.startsWith('m')) {} else {
                if (this.INTERVALS[quality] === undefined && this.INTERVALS[quality.toLowerCase()]) {
                    quality = quality.toLowerCase();
                } else if (this.INTERVALS[quality] === undefined && chordName.length <= 2) {
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
            return intervals.map(interval => this.midiToNoteName(rootMidi + interval, useFlats));
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
    const muteBackingTrackCheckbox = document.getElementById('mute-backing-track');
    const beatIndicators = [
        document.getElementById('beat-1'), document.getElementById('beat-2'),
        document.getElementById('beat-3'), document.getElementById('beat-4')
    ];

    // --- Audio Synthesis ---
    const leadSynth = new Tone.MonoSynth({
        oscillator: { type: 'sawtooth' },
        envelope: { attack: 0.05, decay: 0.2, sustain: 0.7, release: 0.15 },
        filter: { Q: 2, type: 'lowpass', frequency: 1200 },
        filterEnvelope: { attack: 0.06, decay: 0.1, sustain: 0.5, release: 0.2, baseFrequency: 300, octaves: 3.5 }
    }).toDestination();
    leadSynth.volume.value = -6;
    const pianoSynth = new Tone.PolySynth(Tone.Synth, {
        oscillator: { type: 'triangle' },
        envelope: { attack: 0.01, decay: 0.5, sustain: 0.2, release: 1 },
    }).toDestination();
    pianoSynth.volume.value = -12;

    // --- Musical Constants & State ---
    const BEATS_PER_MEASURE = 4;
    const TICKS_PER_BEAT = Tone.Transport.PPQ;
    const TICKS_PER_MEASURE = TICKS_PER_BEAT * BEATS_PER_MEASURE;
    let chordMelodies = {}, progression = [], activeChord = null, currentNoteIndex = 0;
    let isPlaying = false, animationFrameId = null, activeLeadNoteInfo = null;
    let midiKeyDownCount = 0, backingPart = null, beatLoop = null;
    let activeKeys = new Set(); // Changed from spacebarActive

    // --- Initial Setup & Event Listeners ---
    setupMidi();
    setupKeyboardListener();
    bpmSlider.addEventListener('input', (e) => {
        bpmValue.textContent = e.target.value;
        Tone.Transport.bpm.value = e.target.value;
        bpmSlider.blur(); //
    });
    generateButton.addEventListener('click', generatePhrases);
    playStopButton.addEventListener('click', togglePlayback);
    muteBackingTrackCheckbox.addEventListener('change', (e) => {
        pianoSynth.volume.value = e.target.checked ? -Infinity : -12;
        muteBackingTrackCheckbox.blur();
    });

    // --- Beat Animation ---
    function startBeatAnimation() {
        if (beatLoop) beatLoop.stop(0).dispose();
        beatLoop = new Tone.Loop(time => {
            Tone.Draw.schedule(() => {
                const beats = Math.floor(Tone.Transport.position.split(':')[1]);
                beatIndicators.forEach((indicator, index) => {
                    indicator.classList.toggle('active', index === beats);
                });
            }, time);
        }, '4n').start(0);
    }

    function stopBeatAnimation() {
        if (beatLoop) beatLoop.stop(0).dispose();
        beatLoop = null;
        beatIndicators.forEach(indicator => indicator.classList.remove('active'));
    }

    // --- Core Functions ---
    async function generatePhrases() {
        generateButton.disabled = true; playStopButton.disabled = true;
        generateButton.textContent = 'フレーズ生成中...'; statusArea.textContent = 'AIがメロディを考えています...';
        stopPlayback();
        pianoRollContent.innerHTML = ''; pianoRollContent.appendChild(playhead);

        generateButton.classList.add('animate-pulse');
        beatIndicators.forEach((indicator, index) => {
            indicator.style.animationDelay = `${index * 120}ms`;
            indicator.classList.add('generating');
        });

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chord_progression: chordSelect.value, style: styleSelect.value }),
            });
            if (!response.ok) throw new Error(`HTTP Error: ${response.status} - ${await response.text()}`);

            const data = await response.json();
            progression = Object.keys(data.chord_melodies);
            chordMelodies = {};
            for (const chord in data.chord_melodies) {
                const decoded = atob(data.chord_melodies[chord]);
                let accumulatedWait = 0;
                chordMelodies[chord] = decoded.trim().split('\n').map(line => {
                    const [pitch, duration, wait, velocity] = line.split(' ').map(Number);
                    accumulatedWait += wait;
                    return { pitch, duration, wait, velocity, startTime: accumulatedWait - wait };
                }).filter(note => !isNaN(note.pitch));
            }
            updateProgressionDisplay(); drawTimingIndicators();
            playStopButton.disabled = false;
            statusArea.textContent = 'フレーズの準備ができました。さあ、MIDIデバイスやスペースキーでセッションの始まりです！';
        } catch (error) {
            console.error('フレーズ生成に失敗:', error.message);
            statusArea.textContent = `エラー: ${error.message}`;
        } finally {
            generateButton.disabled = false;
            generateButton.textContent = '1. フレーズをAIに生成させる';
            generateButton.classList.remove('animate-pulse');
            beatIndicators.forEach(indicator => {
                indicator.classList.remove('generating');
                indicator.style.animationDelay = '';
            });
        }
    }

    async function togglePlayback() {
        if (progression.length === 0) return;
        await ensureAudioContext();
        isPlaying ? stopPlayback() : startPlayback();
        playStopButton.blur();
    }

    function startPlayback() {
        pianoRollContent.querySelectorAll('.note-block').forEach(note => note.remove());
        scheduleBackingTrack();
        Tone.Transport.seconds = 0; Tone.Transport.start();
        isPlaying = true;
        playStopButton.textContent = '演奏停止';
        playStopButton.classList.replace('bg-teal-600', 'bg-amber-600');
        playStopButton.classList.replace('hover:bg-teal-700', 'hover:bg-amber-700');
        animatePlayhead();
        startBeatAnimation();
    }

    function stopPlayback() {
        Tone.Transport.stop(); Tone.Transport.cancel(0);
        if (backingPart) { backingPart.stop(0).clear().dispose(); backingPart = null; }
        if (leadSynth) leadSynth.triggerRelease();
        if (pianoSynth) pianoSynth.releaseAll();
        activeLeadNoteInfo = null; midiKeyDownCount = 0; activeKeys.clear(); //
        if (animationFrameId) { cancelAnimationFrame(animationFrameId); animationFrameId = null; }
        playhead.style.left = '0%';
        document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-sky-500'));
        activeChord = null; isPlaying = false;
        playStopButton.textContent = '2. 演奏開始';
        playStopButton.classList.replace('bg-amber-600', 'bg-teal-600');
        playStopButton.classList.replace('hover:bg-amber-700', 'hover:bg-teal-700');
        noteDisplayArea.textContent = '...';
        stopBeatAnimation();
    }

    function scheduleBackingTrack() {
        if (backingPart) { backingPart.stop(0).clear().dispose(); backingPart = null; }
        const events = progression.flatMap((chord, measureIndex) => {
            const chordName = chord.split('_')[0];
            const notes = Chord.getVoicing(chordName);
            const measureEvents = [{
                time: Tone.Ticks(measureIndex * TICKS_PER_MEASURE).toSeconds(),
                type: 'update', chord: chord, chordIndex: measureIndex
            }];
            if (notes.length > 0) {
                for (let beat = 0; beat < BEATS_PER_MEASURE; beat++) {
                    const timeInSeconds = Tone.Ticks((measureIndex * TICKS_PER_MEASURE) + (beat * TICKS_PER_BEAT)).toSeconds();
                    measureEvents.push({ time: timeInSeconds, type: 'play', notes: [...notes], duration: '4n' });
                }
            }
            return measureEvents;
        });
        if (events.length === 0) return;
        backingPart = new Tone.Part((time, value) => {
            if (value.type === 'play') {
                pianoSynth.triggerAttackRelease(value.notes, value.duration, time);
            } else if (value.type === 'update') {
                Tone.Draw.schedule(() => {
                    activeChord = value.chord; currentNoteIndex = 0;
                    updateNoteDisplay(chordMelodies[activeChord]);
                    document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-sky-500'));
                    const activeIndicator = document.getElementById(`indicator-${value.chordIndex}`);
                    if (activeIndicator) activeIndicator.classList.add('bg-sky-500');
                }, time);
            }
        }, events).start(0);
        backingPart.loop = true;
        backingPart.loopEnd = Tone.Ticks(progression.length * TICKS_PER_MEASURE).toSeconds();
    }

    async function playNextLeadNote(velocity = 0.75) {
        await ensureAudioContext();
        if (!isPlaying || !activeChord || !chordMelodies[activeChord] || chordMelodies[activeChord].length === 0 || activeLeadNoteInfo) return;
        const notesOfCurrentChord = chordMelodies[activeChord];
        const noteToPlay = notesOfCurrentChord[currentNoteIndex];
        if (!noteToPlay || typeof noteToPlay.pitch !== 'number') return;
        const freq = Tone.Midi(noteToPlay.pitch).toFrequency();
        leadSynth.triggerAttack(freq, Tone.now(), velocity);
        const noteStartTicks = Tone.Transport.ticks;
        const noteElement = drawPlayedNote(noteToPlay.pitch, noteStartTicks);
        activeLeadNoteInfo = { pitch: noteToPlay.pitch, startTicks: noteStartTicks, element: noteElement };
        currentNoteIndex = (currentNoteIndex + 1) % notesOfCurrentChord.length;
    }

    function stopCurrentLeadNote() {
        if (!activeLeadNoteInfo) return;
        leadSynth.triggerRelease(Tone.now());
        const { startTicks, element } = activeLeadNoteInfo;
        const durationTicks = Tone.Transport.ticks - startTicks;
        const totalTicks = progression.length * TICKS_PER_MEASURE;
        if (totalTicks > 0 && element) {
            const widthPercentage = (durationTicks / totalTicks) * 100;
            element.style.width = `${Math.max(0.5, widthPercentage)}%`;
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
        noteBlock.style.left = `${(currentLoopTicks / totalTicks) * 100}%`;
        noteBlock.style.top = `${100 - ((pitch - PITCH_MIN) / PITCH_RANGE) * 100}%`;
        noteBlock.style.height = `${100 / PITCH_RANGE}%`;
        noteBlock.style.width = `1%`;
        pianoRollContent.appendChild(noteBlock);
        return noteBlock;
    }

    function drawTimingIndicators() {
        pianoRollContent.querySelectorAll('.timing-indicator').forEach(ind => ind.remove());
        const totalTicks = progression.length * TICKS_PER_MEASURE;
        if (totalTicks === 0) return;
        progression.forEach((chordKey, measureIndex) => {
            const notes = chordMelodies[chordKey];
            if (!notes) return;
            notes.forEach(note => {
                const indicator = document.createElement('div');
                indicator.className = 'timing-indicator';
                const noteStartTick = measureIndex * TICKS_PER_MEASURE + note.startTime;
                indicator.style.left = `${(noteStartTick / totalTicks) * 100}%`;
                pianoRollContent.appendChild(indicator);
            });
        });
    }

    function updateProgressionDisplay() {
        progressionDisplay.innerHTML = '';
        progression.forEach((chord, index) => {
            const el = document.createElement('div');
            el.id = `indicator-${index}`;
            el.className = 'indicator text-center p-2 rounded-md w-24';
            el.textContent = chord.split('_')[0];
            progressionDisplay.appendChild(el);
        });
    }

    function updateNoteDisplay(notes) {
        noteDisplayArea.textContent = (!notes || notes.length === 0) ? '...' : notes.map(n => Chord.midiToNoteName(n.pitch)).join(' ');
    }

    function animatePlayhead() {
        if (!isPlaying) { animationFrameId = null; return; }
        const totalTicks = progression.length * TICKS_PER_MEASURE;
        if (totalTicks > 0) {
            const currentLoopTicks = Tone.Transport.ticks % totalTicks;
            playhead.style.left = `${(currentLoopTicks / totalTicks) * 100}%`;
        }
        animationFrameId = requestAnimationFrame(animatePlayhead);
    }

    function setupKeyboardListener() {
        const isPlayKey = (e) => e.code === 'Space' || e.code.startsWith('Digit') || e.code.startsWith('Numpad');

        document.addEventListener('keydown', (e) => {
            if (e.target.tagName !== 'BODY' || !isPlayKey(e) || activeKeys.has(e.code)) return;
            e.preventDefault();
            activeKeys.add(e.code);
            if (activeKeys.size === 1) { //
                playNextLeadNote();
            }
        });

        document.addEventListener('keyup', (e) => {
            if (e.target.tagName !== 'BODY' || !isPlayKey(e)) return;
            activeKeys.delete(e.code);
            if (activeKeys.size === 0) { //
                stopCurrentLeadNote();
            }
        });
    }

    function handleMidiNoteOn(velocity = 0.75) {
        if (++midiKeyDownCount === 1) playNextLeadNote(velocity);
    }
    function handleMidiNoteOff() {
        if (midiKeyDownCount > 0 && --midiKeyDownCount === 0) stopCurrentLeadNote();
    }

    async function setupMidi() {
        if (typeof WebMidi === 'undefined' || !navigator.requestMIDIAccess) return;
        try {
            await WebMidi.enable();
            const midiInput = WebMidi.inputs[0];
            if (midiInput) {
                statusArea.textContent = `MIDI In: ${midiInput.name}`;
                midiInput.on("noteon", e => handleMidiNoteOn(e.velocity));
                midiInput.on("noteoff", e => handleMidiNoteOff());
            } else {
                statusArea.textContent = 'MIDIデバイス未接続。PCキーボードで演奏できます。';
            }
        } catch (err) {
            console.error("Could not enable MIDI:", err);
            statusArea.textContent = 'MIDIデバイスの有効化に失敗しました。';
        }
    }

    async function ensureAudioContext() {
        if (Tone.context.state !== 'running') await Tone.start();
    }
});
