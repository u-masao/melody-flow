document.addEventListener('DOMContentLoaded', () => {

    const PRODUCTION_HOSTNAME = "melody-flow.click";
    const CLOUDFRONT_ENDPOINT = "https://melody-flow.click";
    const LOCAL_API_ENDPOINT = "http://localhost:8000";
    const IS_LOCALHOST = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");

    class Chord {
        static NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
        static NOTES_FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
        static INTERVALS = {
            '': [0, 4, 7], 'M7': [0, 4, 7, 11], '7': [0, 4, 7, 10], 'm': [0, 3, 7],
            'm7': [0, 3, 7, 10], 'mM7': [0, 3, 7, 11], 'm7b5': [0, 3, 6, 10],
            'dim': [0, 3, 6], 'dim7': [0, 3, 6, 9], 'aug': [0, 4, 8], 'sus4': [0, 5, 7],
            '7b9': [0, 4, 7, 10]
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
            if (quality.toLowerCase() === 'maj7') quality = 'M7';
            if (quality.toLowerCase() === 'min7') quality = 'm7';
            if (quality.includes('(')) {
                quality = quality.substring(0, quality.indexOf('('));
            }
            const useFlats = rootStr.includes('b');
            const notes = useFlats ? this.NOTES_FLAT : this.NOTES;
            let rootMidi = notes.indexOf(rootStr.charAt(0).toUpperCase() + rootStr.slice(1));
            if (rootMidi === -1) {
                const sharpIndex = this.NOTES.indexOf(rootStr.charAt(0).toUpperCase() + rootStr.slice(1));
                const flatIndex = this.NOTES_FLAT.indexOf(rootStr.charAt(0).toUpperCase() + rootStr.slice(1));
                rootMidi = sharpIndex !== -1 ? sharpIndex : flatIndex;
            }
            if (rootMidi === -1) return [];
            rootMidi += 48;
            const intervals = this.INTERVALS[quality] || this.INTERVALS[''];
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
    const settingsButton = document.getElementById('settings-button');
    const settingsModal = document.getElementById('settings-modal');
    const closeModalButton = document.getElementById('close-modal-button');
    const midiInputSelect = document.getElementById('midi-input-select');
    const tapTempoButton = document.getElementById('tap-tempo-button');
    const playNoteButton = document.getElementById('play-note-button');

    // --- Synths ---
    const leadSynth = new Tone.MonoSynth({
        oscillator: { type: 'sawtooth' },
        envelope: { attack: 0.05, decay: 0.2, sustain: 0.7, release: 0.15 },
        filter: { Q: 2, type: 'lowpass', frequency: 1200 },
        filterEnvelope: { attack: 0.06, decay: 0.1, sustain: 0.5, release: 0.2, baseFrequency: 300, octaves: 3.5 }
    }).toDestination();
    leadSynth.volume.value = -6;
    const pianoSynth = new Tone.PolySynth(Tone.Synth, {
        oscillator: { type: 'triangle' },
        envelope: { attack: 0.01, decay: 0.5, sustain: 0.2, release: 0.7 },
    }).toDestination();
    pianoSynth.volume.value = -12;
    const notificationSynth = new Tone.PolySynth(Tone.Synth).toDestination();
    notificationSynth.volume.value = -12;

    // --- State Variables ---
    const BEATS_PER_MEASURE = 4;
    const TICKS_PER_BEAT = Tone.Transport.PPQ;
    const TICKS_PER_MEASURE = TICKS_PER_BEAT * BEATS_PER_MEASURE;
    let chordMelodies = {}, progression = [], activeChord = null, currentNoteIndex = 0;
    let isPlaying = false, animationFrameId = null, activeLeadNoteInfo = null;
    let midiKeyDownCount = 0, backingPart = null, beatLoop = null;
    let activeKeys = new Set();
    let currentMidiInput = null;

    // --- Initial Setup ---
    setupEventListeners();
    setupMidi();

    function setupEventListeners() {
        bpmSlider.addEventListener('input', (e) => {
            bpmValue.textContent = e.target.value;
            Tone.Transport.bpm.value = e.target.value;
        });
        bpmSlider.addEventListener('click', () => bpmSlider.blur());
        generateButton.addEventListener('click', generatePhrases);
        playStopButton.addEventListener('click', togglePlayback);
        muteBackingTrackCheckbox.addEventListener('change', (e) => {
            pianoSynth.volume.value = e.target.checked ? -Infinity : -12;
            muteBackingTrackCheckbox.blur();
        });
        setupKeyboardListener();

        // Modal listeners
        settingsButton.addEventListener('click', () => {
            settingsModal.classList.remove('hidden');
        });
        closeModalButton.addEventListener('click', () => {
            settingsModal.classList.add('hidden');
        });
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) {
                settingsModal.classList.add('hidden');
            }
        });

        setupTapTempo();

        // Play note button listeners
        playNoteButton.addEventListener('mousedown', () => handleMidiNoteOn());
        playNoteButton.addEventListener('mouseup', () => {
            handleMidiNoteOff();
            playNoteButton.blur(); // ★★★ フォーカスを外す ★★★
        });
        playNoteButton.addEventListener('mouseleave', () => handleMidiNoteOff());
        playNoteButton.addEventListener('touchstart', (e) => {
            e.preventDefault();
            handleMidiNoteOn();
        });
        playNoteButton.addEventListener('touchend', (e) => {
            e.preventDefault();
            handleMidiNoteOff();
            playNoteButton.blur(); // ★★★ フォーカスを外す ★★★
        });
    }

    // ★★★ START: HSVからRGBへ変換するヘルパー関数 ★★★
    function hsvToRgb(h, s, v) {
        let r, g, b;
        let i = Math.floor(h * 6);
        let f = h * 6 - i;
        let p = v * (1 - s);
        let q = v * (1 - f * s);
        let t = v * (1 - (1 - f) * s);
        switch (i % 6) {
            case 0: r = v, g = t, b = p; break;
            case 1: r = q, g = v, b = p; break;
            case 2: r = p, g = v, b = t; break;
            case 3: r = p, g = q, b = v; break;
            case 4: r = t, g = p, b = v; break;
            case 5: r = v, g = p, b = q; break;
        }
        return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
    }
    // ★★★ END: HSVからRGBへ変換するヘルパー関数 ★★★

    function setupTapTempo() {
        let tapTimestamps = [];
        let tapTimeout = null;

        tapTempoButton.addEventListener('click', () => {
            const now = performance.now();
            tapTimestamps.push(now);
            if (tapTimestamps.length > 4) tapTimestamps.shift();
            
            clearTimeout(tapTimeout);
            tapTimeout = setTimeout(() => { tapTimestamps = []; }, 2000);

            if (tapTimestamps.length >= 2) {
                let totalInterval = 0;
                for (let i = 1; i < tapTimestamps.length; i++) {
                    totalInterval += tapTimestamps[i] - tapTimestamps[i - 1];
                }
                const avgInterval = totalInterval / (tapTimestamps.length - 1);
                const newBpm = Math.round(60000 / avgInterval);

                if (newBpm >= 60 && newBpm <= 180) {
                    bpmSlider.value = newBpm;
                    bpmValue.textContent = newBpm;
                    Tone.Transport.bpm.value = newBpm;
                }
            }
        });
    }

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

    async function generatePhrases() {
        await ensureAudioContext();
        generateButton.disabled = true;
        playStopButton.disabled = true;
        playNoteButton.disabled = true;

        stopPlayback();
        pianoRollContent.innerHTML = ''; pianoRollContent.appendChild(playhead);
        generateButton.classList.add('animate-pulse');

        try {
            const chordProgression = chordSelect.value;
            const style = styleSelect.value;
            const isProductionEnv = (window.location.hostname === PRODUCTION_HOSTNAME);
            const variations = isProductionEnv ? 5 : 2;
            let variationNumber;

            if (IS_LOCALHOST) {
                const combinedString = chordProgression + style;
                let charCodeSum = 0;
                for (let i = 0; i < combinedString.length; i++) charCodeSum += combinedString.charCodeAt(i);
                variationNumber = (charCodeSum % variations) + 1;
            } else {
                variationNumber = Math.floor(Math.random() * variations) + 1;
            }

            let requestUrl;
            let data;

            if (IS_LOCALHOST) {
                statusArea.textContent = 'ローカルサーバーでフレーズを生成中...';
                const params = new URLSearchParams({ chord_progression: chordProgression, style: style, variation: variationNumber });
                requestUrl = `${LOCAL_API_ENDPOINT}/generate?${params.toString()}`;
                const response = await fetch(requestUrl);
                if (!response.ok) throw new Error(`API Error: ${response.status}`);
                data = await response.json();
            } else {
                statusArea.textContent = 'キャッシュされたフレーズを読み込んでいます...';
                const progHash = md5(chordProgression);
                requestUrl = `${CLOUDFRONT_ENDPOINT}/api/${progHash}/${style}/${variationNumber}.json`;
                const response = await fetch(requestUrl);
                if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
                data = await response.json();
            }

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

            notificationSynth.triggerAttackRelease(["C5", "G5"], "8n", Tone.now());
            updateProgressionDisplay();
            drawTimingIndicators();
            playStopButton.disabled = false;
            statusArea.textContent = 'フレーズの準備ができました！';
        } catch (error) {
            console.error('フレーズの準備に失敗:', error.message);
            statusArea.textContent = `エラー: ${error.message}`;
            notificationSynth.triggerAttackRelease(["C4", "Eb4"], "8n", Tone.now());
        } finally {
            generateButton.disabled = false;
            generateButton.textContent = '1. フレーズを準備する';
            generateButton.classList.remove('animate-pulse');
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
        playNoteButton.disabled = false;
        animatePlayhead();
        startBeatAnimation();
    }

    function stopPlayback() {
        Tone.Transport.stop(); Tone.Transport.cancel(0);
        if (backingPart) { backingPart.stop(0).clear().dispose(); backingPart = null; }
        if (leadSynth) leadSynth.triggerRelease();
        if (pianoSynth) pianoSynth.releaseAll();
        activeLeadNoteInfo = null;
        if (midiKeyDownCount > 0) { // ★★★ もし音が鳴りっぱなしなら、ボタンの色をリセット ★★★
            midiKeyDownCount = 0;
            handleMidiNoteOff();
        }
        activeKeys.clear();
        if (animationFrameId) { cancelAnimationFrame(animationFrameId); animationFrameId = null; }
        playhead.style.left = '0%';
        document.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-sky-500'));
        activeChord = null; isPlaying = false;
        playStopButton.textContent = '2. 演奏開始';
        playStopButton.classList.replace('bg-amber-600', 'bg-teal-600');
        playStopButton.classList.replace('hover:bg-amber-700', 'hover:bg-teal-700');
        playNoteButton.disabled = true;
        noteDisplayArea.textContent = '...';
        stopBeatAnimation();
    }

    function scheduleBackingTrack() {
        if (backingPart) { backingPart.stop(0).clear().dispose(); backingPart = null; }
        const shuffleDuration = Tone.Time('8t').toSeconds() * 2;
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
                    measureEvents.push({ time: timeInSeconds, type: 'play', notes: [...notes], duration: shuffleDuration });
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
        const totalMeasures = progression.length;
        if (totalMeasures <= 1) return;
        for (let i = 1; i < totalMeasures; i++) {
            const indicator = document.createElement('div');
            indicator.className = 'timing-indicator';
            indicator.style.left = `${(i / totalMeasures) * 100}%`;
            indicator.style.backgroundColor = 'rgba(255, 255, 255, 0.25)';
            indicator.style.width = '2px';
            pianoRollContent.appendChild(indicator);
        }
    }

    function updateProgressionDisplay() {
        progressionDisplay.innerHTML = '';
        progression.forEach((chord, index) => {
            const el = document.createElement('div');
            el.id = `indicator-${index}`;
            el.className = 'indicator text-center p-2 rounded-md flex-shrink-0';
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
            if (activeKeys.size === 1) handleMidiNoteOn();
        });

        document.addEventListener('keyup', (e) => {
            if (e.target.tagName !== 'BODY' || !isPlayKey(e)) return;
            activeKeys.delete(e.code);
            if (activeKeys.size === 0) handleMidiNoteOff();
        });
    }

    // ★★★ START: Note On/Off ハンドラを修正 ★★★
    function handleMidiNoteOn(velocity = 0.75) {
        if (midiKeyDownCount === 0) {
            // 色をアクティブ状態に変更
            playNoteButton.style.backgroundColor = ''; // インラインスタイルをリセット
            playNoteButton.classList.remove('bg-indigo-600', 'hover:bg-indigo-700');
            playNoteButton.classList.add('bg-purple-500');
        }
        if (++midiKeyDownCount === 1) {
            playNextLeadNote(velocity);
        }
    }

    function handleMidiNoteOff() {
        if (midiKeyDownCount > 0 && --midiKeyDownCount === 0) {
            stopCurrentLeadNote();
            // 色を非アクティブ状態に戻す
            playNoteButton.style.backgroundColor = ''; // インラインスタイルをリセット
            playNoteButton.classList.remove('bg-purple-500');
            playNoteButton.classList.add('bg-indigo-600', 'hover:bg-indigo-700');
        }
    }
    // ★★★ END: Note On/Off ハンドラを修正 ★★★

    // ★★★ START: アフタータッチハンドラを修正 ★★★
    function handleMidiChannelAftertouch(value) {
        if (midiKeyDownCount > 0 && leadSynth) {
            const now = Tone.now();
            const timeConstant = 0.02;

            // 1. シンセのパラメータを更新
            const newFrequency = 1200 + (3800 * value);
            leadSynth.filter.frequency.setTargetAtTime(newFrequency, now, timeConstant);
            const newVolume = -12 + (10 * value);
            leadSynth.volume.setTargetAtTime(newVolume, now, timeConstant);

            // 2. ボタンの彩度を更新
            const hue = 260; // 紫系の色相
            const saturation = 100 - (80 * value); // 0.0-1.0の値を彩度100%-20%にマッピング
            const brightness = 80; // 明度は固定
            const [r, g, b] = hsvToRgb(hue / 360, saturation / 100, brightness / 100);
            
            // CSSクラスによる背景色指定を上書きするため、インラインスタイルを直接設定
            playNoteButton.classList.remove('bg-indigo-600', 'hover:bg-indigo-700', 'bg-purple-500');
            playNoteButton.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
        }
    }
    // ★★★ END: アフタータッチハンドラを修正 ★★★

    function attachMidiListeners(inputId) {
        if (currentMidiInput) {
            currentMidiInput.removeListener("noteon");
            currentMidiInput.removeListener("noteoff");
            currentMidiInput.removeListener("channelaftertouch");
        }
        currentMidiInput = WebMidi.getInputById(inputId);

        if (currentMidiInput) {
            statusArea.textContent = `MIDI In: ${currentMidiInput.name}`;
            currentMidiInput.on("noteon", e => handleMidiNoteOn(e.velocity));
            currentMidiInput.on("noteoff", e => handleMidiNoteOff());
            currentMidiInput.on("channelaftertouch", e => handleMidiChannelAftertouch(e.value));
        } else {
             statusArea.textContent = 'MIDIデバイス未接続。スペースキー等で演奏できます。';
        }
    }

    function populateMidiDeviceList() {
        if (WebMidi.inputs.length > 0) {
            const previouslySelectedId = midiInputSelect.value;
            midiInputSelect.innerHTML = '';
            WebMidi.inputs.forEach(input => {
                const option = document.createElement('option');
                option.value = input.id;
                option.textContent = input.name;
                midiInputSelect.appendChild(option);
            });
            const stillExists = WebMidi.inputs.some(input => input.id === previouslySelectedId);
            if (stillExists) {
                midiInputSelect.value = previouslySelectedId;
            }
            attachMidiListeners(midiInputSelect.value);
        } else {
            midiInputSelect.innerHTML = '<option>利用可能なデバイスがありません</option>';
            if(currentMidiInput) {
                attachMidiListeners(null);
            } else {
                statusArea.textContent = 'MIDIデバイス未接続。スペースキー等で演奏できます。';
            }
        }
    }

    async function setupMidi() {
        if (typeof WebMidi === 'undefined' || !navigator.requestMIDIAccess) {
            settingsButton.style.display = 'none';
            return;
        }

        try {
            await WebMidi.enable();
            populateMidiDeviceList();
            midiInputSelect.addEventListener('change', (e) => attachMidiListeners(e.target.value));
            WebMidi.addListener("connected", () => populateMidiDeviceList());
            WebMidi.addListener("disconnected", () => populateMidiDeviceList());
        } catch (err) {
            console.error("Could not enable MIDI:", err);
            statusArea.textContent = 'MIDIデバイスの有効化に失敗しました。';
            midiInputSelect.innerHTML = '<option>MIDIの有効化に失敗</option>';
            settingsButton.style.display = 'none';
        }
    }

    async function ensureAudioContext() {
        if (Tone.context.state !== 'running') await Tone.start();
    }
});
