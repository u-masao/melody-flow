document.addEventListener('DOMContentLoaded', () => {

    // --- トラッキング用コード START ---

    /**
     * ユーザーIDをlocalStorageから取得または新規作成する
     * @returns {string} ユーザーID
     */
    function getUserId() {
        let userId = localStorage.getItem('melodyFlowUserId');
        if (!userId) {
            userId = self.crypto.randomUUID();
            localStorage.setItem('melodyFlowUserId', userId);
        }
        return userId;
    }

    const USER_ID = getUserId();
    const IS_PRODUCTION = window.location.hostname === 'melody-flow.click';

    /**
     * イベントをトラッキングサービスに送信するラッパー関数
     * @param {string} eventName - イベント名 (snake_case形式)
     * @param {object} [properties={}] - イベントに紐付けるプロパティ
     * @param {boolean} [useBeacon=false] - ページ離脱時など確実性が求められる場合 true
     */
    function trackEvent(eventName, properties = {}, useBeacon = false) {
        // 本番環境以外ではコンソールに出力するのみ
        if (!IS_PRODUCTION) {
            console.log(`[TRACKING SKIPPED] Event: ${eventName}`, { user_id: USER_ID, ...properties });
            return;
        }

        // gtag関数が存在しない場合は何もしない
        if (typeof gtag === 'function' && !useBeacon) {
            const eventData = { user_id: USER_ID, ...properties };
            // 高頻度イベントはブラウザのアイドル時に実行
            if (eventName === 'play_note' && 'requestIdleCallback' in window) {
                requestIdleCallback(() => {
                    gtag('event', eventName, eventData);
                });
            } else {
                gtag('event', eventName, eventData);
            }
            return;
        }

        // ページ離脱時など、信頼性が重要なイベントはビーコンを使う
        if (useBeacon && 'sendBeacon' in navigator) {
            const proxyUrl = '/track'; // CloudFrontのパスパターン
            const data = new Blob([JSON.stringify({ eventName, properties, userId: USER_ID })], { type: 'application/json' });
            navigator.sendBeacon(proxyUrl, data);
        }
    }

    // ページ表示イベントを最初に送信
    trackEvent('page_view');

    // --- トラッキング用コード END ---


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

        static parseChord(chordName) {
            if (!chordName) return null;
            let rootStr, quality;
            if (chordName.length > 1 && (chordName[1] === '#' || chordName[1] === 'b')) {
                rootStr = chordName.substring(0, 2);
                quality = chordName.substring(2);
            } else {
                rootStr = chordName.substring(0, 1);
                quality = chordName.substring(1);
            }
            return { root: rootStr, quality: quality };
        }

        static transpose(chordName, semitones, preferFlats = false) {
            const parsed = this.parseChord(chordName);
            if (!parsed) return chordName;

            const { root, quality } = parsed;
            let rootIndex = this.NOTES.indexOf(root);
            if (rootIndex === -1) rootIndex = this.NOTES_FLAT.indexOf(root);
            if (rootIndex === -1) return chordName;

            const newRootIndex = (rootIndex + semitones + 24) % 12;
            const sharpNote = this.NOTES[newRootIndex];
            const flatNote = this.NOTES_FLAT[newRootIndex];
            let newRoot = preferFlats && sharpNote !== flatNote ? flatNote : sharpNote;
            return newRoot + quality;
        }
    }

    // --- DOM Elements ---
    const mainContainer = document.getElementById('main-container');
    const chordSelect = document.getElementById('chord-progression');
    const keySelect = document.getElementById('key-select');
    const styleSelect = document.getElementById('music-style');
    const generateButton = document.getElementById('generate-button');
    const bpmSlider = document.getElementById('bpm-slider');
    const bpmValue = document.getElementById('bpm-value');
    const playStopButton = document.getElementById('play-stop-button');
    const playIcon = document.getElementById('play-icon');
    const stopIcon = document.getElementById('stop-icon');
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
    const closeSettingsButton = document.getElementById('close-settings-button');
    const midiInputSelect = document.getElementById('midi-input-select');
    const tapTempoButton = document.getElementById('tap-tempo-button');
    const playNoteButton = document.getElementById('play-note-button');
    const playHint = document.getElementById('play-hint');
    const modeToggle = document.getElementById('mode-toggle');
    const helpButton = document.getElementById('help-button');
    const helpModal = document.getElementById('help-modal');
    const closeHelpButton = document.getElementById('close-help-button');

    // --- Initial Generate Button Content ---
    const initialGenerateButtonHTML = generateButton ? generateButton.innerHTML : '';

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
    let playbackStartTime = 0;
   
    // --- Analytics Variables ---
    let sessionAnalytics = {};
    function resetSessionAnalytics() {
        sessionAnalytics = {
            velocities: [],
            aftertouchValues: [],
            noteOnCount: 0,
            aftertouchCount: 0
        };
    }
    resetSessionAnalytics(); // Initialize

    // --- Initial Setup ---
    setupEventListeners();
    setupMidi();
    displayTransposedPreview();

    function setupEventListeners() {
        const ALL_KEYS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B', 'C#', 'D#', 'F#', 'G#', 'A#'];
        if (keySelect) {
            keySelect.innerHTML = '';
            const sortedKeys = ['C', 'C#', 'Db', 'D', 'D#', 'Eb', 'E', 'F', 'F#', 'Gb', 'G', 'G#', 'Ab', 'A', 'A#', 'Bb', 'B'];
            sortedKeys.forEach(key => {
                const option = document.createElement('option');
                option.value = key; option.textContent = key;
                keySelect.appendChild(option);
            });
            keySelect.value = 'C';
        }

        const resetOptions = () => {
            displayTransposedPreview();
            resetGenerateButtonState();
        };

        if(chordSelect) chordSelect.addEventListener('change', (e) => {
            resetOptions();
            trackEvent('change_setting', {
                setting_name: 'chord_progression',
                value: e.target.options[e.target.selectedIndex].text
            });
        });
        if(keySelect) keySelect.addEventListener('change', (e) => {
            resetOptions();
            trackEvent('change_setting', {
                setting_name: 'key',
                value: e.target.value
            });
        });
        if(styleSelect) styleSelect.addEventListener('change', (e) => {
            resetOptions();
            trackEvent('change_setting', {
                setting_name: 'style',
                value: e.target.value
            });
        });

        if(bpmSlider) {
             bpmSlider.addEventListener('input', (e) => {
                if(bpmValue) bpmValue.textContent = e.target.value;
             });
             bpmSlider.addEventListener('change', (e) => {
                Tone.Transport.bpm.value = e.target.value;
                trackEvent('change_setting', {
                    setting_name: 'bpm',
                    value: e.target.value,
                    method: 'slider'
                });
             });
             bpmSlider.addEventListener('click', () => bpmSlider.blur());
        }

        if(generateButton) generateButton.addEventListener('click', generatePhrases);
        if(playStopButton) playStopButton.addEventListener('click', togglePlayback);

        if(muteBackingTrackCheckbox) muteBackingTrackCheckbox.addEventListener('change', (e) => {
            pianoSynth.volume.value = e.target.checked ? -Infinity : -12;
            muteBackingTrackCheckbox.blur();
            trackEvent('change_setting', {
                setting_name: 'mute_backing_track',
                value: e.target.checked
            });
        });

        if(modeToggle) modeToggle.addEventListener('change', (e) => {
            document.body.classList.toggle('studio-mode', e.target.checked);
            trackEvent('change_setting', {
                setting_name: 'mode',
                value: e.target.checked ? 'studio' : 'play'
            });
        });

        if(helpButton) helpButton.addEventListener('click', () => {
            helpModal.classList.remove('hidden');
            trackEvent('open_modal', { modal_name: 'help' });
        });
        if(closeHelpButton) closeHelpButton.addEventListener('click', () => helpModal.classList.add('hidden'));
        if(helpModal) helpModal.addEventListener('click', (e) => { if (e.target === helpModal) helpModal.classList.add('hidden'); });

        if(settingsButton) settingsButton.addEventListener('click', () => {
            settingsModal.classList.remove('hidden');
            trackEvent('open_modal', { modal_name: 'settings' });
        });
        if(closeSettingsButton) closeSettingsButton.addEventListener('click', () => settingsModal.classList.add('hidden'));
        if(settingsModal) settingsModal.addEventListener('click', (e) => { if (e.target === settingsModal) settingsModal.classList.add('hidden'); });

        if(tapTempoButton) setupTapTempo();
        if(playNoteButton) {
            playNoteButton.addEventListener('mousedown', () => handleMidiNoteOn(0.75, 'button'));
            playNoteButton.addEventListener('mouseup', () => handleMidiNoteOff('button'));
            playNoteButton.addEventListener('mouseleave', () => { if (midiKeyDownCount > 0) handleMidiNoteOff('button'); });
            playNoteButton.addEventListener('touchstart', (e) => { e.preventDefault(); handleMidiNoteOn(0.75, 'button'); });
            playNoteButton.addEventListener('touchend', (e) => { e.preventDefault(); handleMidiNoteOff('button'); });
        }

        setupKeyboardListener();
    }

    function resetGenerateButtonState() {
        if (!generateButton) return;
        generateButton.disabled = false;
        generateButton.innerHTML = initialGenerateButtonHTML;
        generateButton.classList.remove('bg-gray-700', 'cursor-not-allowed', 'opacity-50');
        generateButton.classList.add('bg-indigo-600', 'hover:bg-indigo-700');
        if (playStopButton) playStopButton.disabled = true;
        if (playNoteButton) playNoteButton.disabled = true;
    }

    function displayTransposedPreview() {
        if (!chordSelect || !keySelect || !progressionDisplay) return;
        const selectedValue = chordSelect.value;
        const parts = selectedValue.split(':');
        if (parts.length < 2) return;

        const originalKey = parts[0].trim();
        const originalProgressionString = parts[1].trim();
        const targetKey = keySelect.value;
        let finalProgressionString = originalProgressionString;

        let originalKeyIndex = Chord.NOTES.indexOf(originalKey);
        if (originalKeyIndex === -1) originalKeyIndex = Chord.NOTES_FLAT.indexOf(originalKey);
        let targetKeyIndex = Chord.NOTES.indexOf(targetKey);
        if (targetKeyIndex === -1) targetKeyIndex = Chord.NOTES_FLAT.indexOf(targetKey);

        if (originalKeyIndex !== -1 && targetKeyIndex !== -1) {
            const semitones = targetKeyIndex - originalKeyIndex;
            const originalChords = originalProgressionString.split(' - ');
            const FLAT_KEYS = ['F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb'];
            const preferFlats = FLAT_KEYS.includes(targetKey) || targetKey.includes('b');
            finalProgressionString = originalChords.map(chord => Chord.transpose(chord, semitones, preferFlats)).join(' - ');
        }

        const chordsToDisplay = finalProgressionString.split(' - ');
        progressionDisplay.innerHTML = '';
        chordsToDisplay.forEach((chord) => {
            const el = document.createElement('div');
            el.className = 'indicator text-center p-2 rounded-md flex-shrink-0 bg-gray-700/50';
            el.textContent = chord;
            progressionDisplay.appendChild(el);
        });
    }

    function hsvToRgb(h, s, v) {
        let r, g, b; let i = Math.floor(h * 6); let f = h * 6 - i;
        let p = v * (1 - s); let q = v * (1 - f * s); let t = v * (1 - (1 - f) * s);
        switch (i % 6) {
            case 0: r = v, g = t, b = p; break; case 1: r = q, g = v, b = p; break;
            case 2: r = p, g = v, b = t; break; case 3: r = p, g = q, b = v; break;
            case 4: r = t, g = p, b = v; break; case 5: r = v, g = p, b = q; break;
        }
        return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
    }

    function setupTapTempo() {
        let tapTimestamps = []; let tapTimeout = null;
        tapTempoButton.addEventListener('click', () => {
            const now = performance.now();
            tapTimestamps.push(now);
            if (tapTimestamps.length > 4) tapTimestamps.shift();
            clearTimeout(tapTimeout);
            tapTimeout = setTimeout(() => { tapTimestamps = []; }, 2000);
            if (tapTimestamps.length >= 2) {
                const avgInterval = (tapTimestamps[tapTimestamps.length - 1] - tapTimestamps[0]) / (tapTimestamps.length - 1);
                const newBpm = Math.round(60000 / avgInterval);
                if (newBpm >= 60 && newBpm <= 180) {
                    bpmSlider.value = newBpm;
                    bpmValue.textContent = newBpm;
                    Tone.Transport.bpm.value = newBpm;
                    trackEvent('change_setting', {
                        setting_name: 'bpm',
                        value: newBpm,
                        method: 'tap'
                    });
                }
            }
        });
    }

    function startBeatAnimation() {
        if (beatLoop) beatLoop.stop(0).dispose();
        beatLoop = new Tone.Loop(time => {
            Tone.Draw.schedule(() => {
                const beats = Math.floor(Tone.Transport.position.split(':')[1]);
                if (beatIndicators) beatIndicators.forEach((indicator, index) => {
                    if(indicator) indicator.classList.toggle('active', index === beats);
                });
            }, time);
        }, '4n').start(0);
    }

    function stopBeatAnimation() {
        if (beatLoop) beatLoop.stop(0).dispose();
        beatLoop = null;
        if (beatIndicators) beatIndicators.forEach(indicator => indicator && indicator.classList.remove('active'));
    }

    async function generatePhrases() {
        // ガード節：必要なUI要素がDOMに存在するかを確認
        if (!chordSelect || !keySelect || !styleSelect) {
            const errorMessage = "エラー: UI要素（コード進行、キー、スタイル選択）が見つかりません。HTMLのIDが正しいか確認してください。";
            console.error(errorMessage);
            if (statusArea) statusArea.textContent = errorMessage;
            return;
        }

        await ensureAudioContext();

        trackEvent('generate_melody', {
            chord_progression: chordSelect.options[chordSelect.selectedIndex].text,
            key: keySelect.value,
            style: styleSelect.value
        });
        const startTime = performance.now();

        generateButton.disabled = true;
        if(playStopButton) playStopButton.disabled = true;
        if(playNoteButton) playNoteButton.disabled = true;
        stopPlayback();
        if(pianoRollContent && playhead) {
            pianoRollContent.innerHTML = '';
            pianoRollContent.appendChild(playhead);
        }
        generateButton.classList.add('animate-pulse');
        if (statusArea) statusArea.textContent = 'AIがあなたのためのメロディを考えています...';

        try {
            const selectedValue = chordSelect.value;
            const parts = selectedValue.split(':');
            const originalKey = parts[0].trim();
            const originalProgressionString = parts[1].trim();
            const targetKey = keySelect.value;
            const style = styleSelect.value;
            let chordProgression = originalProgressionString;

            let originalKeyIndex = Chord.NOTES.indexOf(originalKey);
            if (originalKeyIndex === -1) originalKeyIndex = Chord.NOTES_FLAT.indexOf(originalKey);
            let targetKeyIndex = Chord.NOTES.indexOf(targetKey);
            if (targetKeyIndex === -1) targetKeyIndex = Chord.NOTES_FLAT.indexOf(targetKey);

            if (originalKeyIndex !== -1 && targetKeyIndex !== -1) {
                const semitones = targetKeyIndex - originalKeyIndex;
                if (semitones !== 0) {
                    const originalChords = originalProgressionString.split(' - ');
                    const FLAT_KEYS = ['F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb'];
                    const preferFlats = FLAT_KEYS.includes(targetKey) || targetKey.includes('b');
                    chordProgression = originalChords.map(chord => Chord.transpose(chord, semitones, preferFlats)).join(' - ');
                }
            }

            const isProductionEnv = (window.location.hostname === PRODUCTION_HOSTNAME);
            const variations = isProductionEnv ? 5 : 2;
            let variationNumber = IS_LOCALHOST ? 1 : Math.floor(Math.random() * variations) + 1;

            const params = new URLSearchParams({ chord_progression: chordProgression, style: style, variation: variationNumber });
            let requestUrl = IS_LOCALHOST ? `${LOCAL_API_ENDPOINT}/generate?${params.toString()}` : `${CLOUDFRONT_ENDPOINT}/api/${md5(chordProgression)}/${style}/${variationNumber}.json`;
            if(!IS_LOCALHOST && statusArea) statusArea.textContent = 'キャッシュされたフレーズを読み込んでいます...';

            const response = await fetch(requestUrl);
            const durationMs = performance.now() - startTime;

            if (!response.ok) throw new Error(`API Error: ${response.status}`);
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

            trackEvent('generate_melody_success', {
                duration_ms: Math.round(durationMs),
                source: IS_LOCALHOST || requestUrl.includes('/generate?') ? 'api' : 'cache'
            });

            notificationSynth.triggerAttackRelease(["C5", "G5"], "8n", Tone.now());
            updateProgressionDisplay();
            drawTimingIndicators();
            if(playStopButton) playStopButton.disabled = false;
            if(statusArea) statusArea.textContent = '準備完了！▶️演奏ボタンを押して🎵をクリックしてください';
            if(generateButton) {
                generateButton.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg><span>準備完了！</span>`;
                generateButton.disabled = true;
                generateButton.classList.remove('bg-indigo-600', 'hover:bg-indigo-700');
                generateButton.classList.add('bg-gray-700', 'cursor-not-allowed', 'opacity-50');
            }
        } catch (error) {
            trackEvent('generate_melody_failed', {
                error_message: error.message,
                duration_ms: Math.round(performance.now() - startTime)
            });
            console.error('フレーズの準備に失敗:', error.message);
            if(statusArea) statusArea.textContent = `エラー: ${error.message}`;
            notificationSynth.triggerAttackRelease(["C4", "Eb4"], "8n", Tone.now());
            resetGenerateButtonState();
        } finally {
            if(generateButton) {
                generateButton.classList.remove('animate-pulse');
            }
        }
    }

    async function togglePlayback() {
        if (progression.length === 0) return;
        await ensureAudioContext();
        isPlaying ? stopPlayback() : startPlayback();
        if(playStopButton) playStopButton.blur();
    }

    function startPlayback() {
        if(pianoRollContent) pianoRollContent.querySelectorAll('.note-block').forEach(note => note.remove());

        if (progression.length > 0) {
            activeChord = progression[0];
            currentNoteIndex = 0;
            updateNoteDisplay(chordMelodies[activeChord]);
            if (progressionDisplay) {
                progressionDisplay.querySelectorAll('.indicator').forEach((el, index) => {
                    el.classList.toggle('bg-sky-500', index === 0);
                    el.classList.toggle('scale-110', index === 0);
                });
            }
        }
       
        resetSessionAnalytics();
        scheduleBackingTrack();
        Tone.Transport.seconds = 0; Tone.Transport.start();
        isPlaying = true;
        playbackStartTime = performance.now();
        trackEvent('start_playback', { bpm: Tone.Transport.bpm.value });

        if(playStopButton) {
            playStopButton.classList.replace('bg-teal-600', 'bg-amber-600');
            playStopButton.classList.replace('hover:bg-teal-700', 'hover:bg-amber-700');
        }
        if (playIcon) playIcon.classList.add('hidden');
        if (stopIcon) stopIcon.classList.remove('hidden');
        if(playNoteButton) playNoteButton.disabled = false;
        if(playHint) playHint.classList.remove('opacity-0');
        animatePlayhead();
        startBeatAnimation();
    }

    function stopPlayback() {
        if (isPlaying) {
            sendSessionAnalytics();
            const durationSec = (performance.now() - playbackStartTime) / 1000;
            trackEvent('stop_playback', {
                playback_duration_sec: Math.round(durationSec)
            }, true);
        }

        Tone.Transport.stop(); Tone.Transport.cancel(0);
        if (backingPart) { backingPart.stop(0).clear().dispose(); backingPart = null; }

        if (activeLeadNoteInfo) {
            stopCurrentLeadNote();
        } else {
            leadSynth.triggerRelease();
        }
        pianoSynth.releaseAll();
        midiKeyDownCount = 0;
        activeKeys.clear();
        if(playNoteButton) {
            playNoteButton.style.backgroundColor = '';
            playNoteButton.classList.remove('bg-purple-500');
            playNoteButton.classList.add('bg-indigo-600', 'hover:bg-indigo-700');
        }

        if (animationFrameId) { cancelAnimationFrame(animationFrameId); animationFrameId = null; }
        if(playhead) playhead.style.left = '0%';
        if(progressionDisplay) progressionDisplay.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-sky-500', 'scale-110'));
        activeChord = null;
        isPlaying = false;

        if(playStopButton) {
            playStopButton.classList.replace('bg-amber-600', 'bg-teal-600');
            playStopButton.classList.replace('hover:bg-amber-700', 'hover:bg-teal-700');
        }
        if (playIcon) playIcon.classList.remove('hidden');
        if (stopIcon) stopIcon.classList.add('hidden');
        if(playNoteButton) playNoteButton.disabled = true;
        if(playHint) playHint.classList.add('opacity-0');
        if(noteDisplayArea) noteDisplayArea.textContent = '...';
        stopBeatAnimation();
    }

    function scheduleBackingTrack() {
        if (backingPart) { backingPart.stop(0).clear().dispose(); backingPart = null; }

        let events = progression.flatMap((chord, measureIndex) => {
            const chordName = chord.split('_')[0];
            const notes = Chord.getVoicing(chordName);
            const measureEvents = [{ time: `${measureIndex}m`, type: 'update', chord: chord, chordIndex: measureIndex }];
            if (notes.length > 0) {
                for (let beat = 0; beat < 4; beat++) {
                    const isBackbeat = (beat === 1 || beat === 3);
                    const velocity = isBackbeat ? 0.9 : 0.6; // バックビートを強く
                    const duration = '4t'; // Note Offをシャッフルっぽく（3連符の長さ）

                    measureEvents.push({
                        time: `${measureIndex}:${beat}:0`,
                        type: 'play',
                        notes: notes,
                        duration: duration,
                        velocity: velocity
                    });
                }
            }
            return measureEvents;
        });

        if (progression.length > 0) {
            const reportTime = Tone.Time(`${progression.length}m`).toSeconds() - 0.1;
            if (reportTime > 0) {
                events.push({ time: reportTime, type: 'report_analytics' });
            }
        }

        if (events.length === 0) return;
        backingPart = new Tone.Part((time, value) => {
            if (value.type === 'play') {
                pianoSynth.triggerAttackRelease(value.notes, value.duration, time, value.velocity);
            } else if (value.type === 'update') {
                Tone.Draw.schedule(() => {
                    activeChord = value.chord; currentNoteIndex = 0;
                    updateNoteDisplay(chordMelodies[activeChord]);
                    if(progressionDisplay) progressionDisplay.querySelectorAll('.indicator').forEach(el => el.classList.remove('bg-sky-500', 'scale-110'));
                    const activeIndicator = document.getElementById(`indicator-${value.chordIndex}`);
                    if (activeIndicator) activeIndicator.classList.add('bg-sky-500', 'scale-110');
                }, time);
            } else if (value.type === 'report_analytics') {
                Tone.Draw.schedule(() => {
                    sendSessionAnalytics();
                    resetSessionAnalytics();
                }, time);
            }
        }, events).start(0);
        backingPart.loop = true;
        backingPart.loopEnd = `${progression.length}m`;
    }

    async function playNextLeadNote(velocity = 0.75) {
        await ensureAudioContext();
        if (!isPlaying || !activeChord || !chordMelodies[activeChord] || chordMelodies[activeChord].length === 0) return;
       
        if (activeLeadNoteInfo) {
            stopCurrentLeadNote();
        }

        const notesOfCurrentChord = chordMelodies[activeChord];
        const noteToPlay = notesOfCurrentChord[currentNoteIndex];
        if (!noteToPlay || typeof noteToPlay.pitch !== 'number') return;
       
        const now = Tone.now();
        const freq = Tone.Midi(noteToPlay.pitch).toFrequency();

        if (activeLeadNoteInfo && activeLeadNoteInfo.vibratoLFO) {
            activeLeadNoteInfo.vibratoLFO.dispose();
        }

        const bpm = Tone.Transport.bpm.value;
        const vibratoFrequency = (bpm / 60) * 2;

        const vibratoLFO = new Tone.LFO({
            frequency: vibratoFrequency,
            type: 'sine',
            min: -20,
            max: 20,
        }).connect(leadSynth.detune).start(now);

        const oneBeatInSeconds = 60 / bpm;
        const startRampTime = now + (2 * oneBeatInSeconds);
        const maxRampTime = now + (5 * oneBeatInSeconds);

        vibratoLFO.amplitude.setValueAtTime(0, now);
        vibratoLFO.amplitude.setValueAtTime(0, startRampTime);
        vibratoLFO.amplitude.linearRampToValueAtTime(1, maxRampTime);

        leadSynth.triggerAttack(freq, now, velocity);
        const noteStartTicks = Tone.Transport.ticks;
        const noteElement = drawPlayedNote(noteToPlay.pitch, noteStartTicks);

        activeLeadNoteInfo = {
            pitch: noteToPlay.pitch,
            startTicks: noteStartTicks,
            element: noteElement,
            element2: null, // ループをまたぐノートの後半部分
            vibratoLFO: vibratoLFO,
            colorStops: [{
                ticks: noteStartTicks,
                color: 'rgba(99, 102, 241, 0.8)'
            }]
        };
        currentNoteIndex = (currentNoteIndex + 1) % notesOfCurrentChord.length;
    }

    function stopCurrentLeadNote() {
        if (!activeLeadNoteInfo) return;
       
        if (activeLeadNoteInfo.vibratoLFO) {
            const now = Tone.now();
            activeLeadNoteInfo.vibratoLFO.stop(now).dispose();
        }

        leadSynth.triggerRelease(Tone.now());
        const { startTicks, element, element2, colorStops } = activeLeadNoteInfo;
        const durationTicks = Tone.Transport.ticks - startTicks;
        const totalTicks = progression.length * TICKS_PER_MEASURE;

        if (totalTicks > 0 && element) {
            const startLoopTicks = startTicks % totalTicks;
           
            if (startLoopTicks + durationTicks > totalTicks) {
                // ループをまたぐ場合
                const width1_ticks = totalTicks - startLoopTicks;
                element.style.width = `${Math.max(0.5, (width1_ticks / totalTicks) * 100)}%`;
                updateNoteGradient(element, startTicks, durationTicks, colorStops);

                if (element2) {
                    const width2_ticks = durationTicks - width1_ticks;
                    element2.style.width = `${Math.max(0.5, (width2_ticks / totalTicks) * 100)}%`;
                    element2.style.background = element.style.background;
                }
            } else {
                // ループをまたがない場合
                const widthPercentage = (durationTicks / totalTicks) * 100;
                element.style.width = `${Math.max(0.5, widthPercentage)}%`;
                updateNoteGradient(element, startTicks, durationTicks, colorStops);
                if (element2) element2.style.width = '0%';
            }
        }
        activeLeadNoteInfo = null;
    }

    function drawPlayedNote(pitch, startTicks) {
        const PITCH_MIN = 48, PITCH_MAX = 84, PITCH_RANGE = PITCH_MAX - PITCH_MIN;
        const noteBlock = document.createElement('div');
        noteBlock.className = 'note-block';
        const totalTicks = progression.length * TICKS_PER_MEASURE;
        if (totalTicks === 0) return null;
        const clampedPitch = Math.max(PITCH_MIN, Math.min(pitch, PITCH_MAX));
        const topPercentage = 100 - ((clampedPitch - PITCH_MIN) / PITCH_RANGE) * 100;

        const currentLoopTicks = startTicks % totalTicks;
        noteBlock.style.left = `${(currentLoopTicks / totalTicks) * 100}%`;
        noteBlock.style.top = `${topPercentage}%`;
        noteBlock.style.height = `${100 / PITCH_RANGE}%`;
        noteBlock.style.width = `0.5%`;
        noteBlock.style.backgroundColor = `rgba(99, 102, 241, 0.8)`;
        if (pianoRollContent) pianoRollContent.appendChild(noteBlock);
        return noteBlock;
    }

    function drawTimingIndicators() {
        if (!pianoRollContent) return;
        pianoRollContent.querySelectorAll('.timing-indicator').forEach(ind => ind.remove());
        const totalMeasures = progression.length;
        if (totalMeasures <= 1) return;
        for (let i = 1; i < totalMeasures; i++) {
            const indicator = document.createElement('div');
            indicator.className = 'timing-indicator';
            indicator.style.left = `${(i / totalMeasures) * 100}%`;
            pianoRollContent.appendChild(indicator);
        }
    }

    function updateProgressionDisplay() {
        if (!progressionDisplay) return;
        progressionDisplay.innerHTML = '';
        progression.forEach((chord, index) => {
            const el = document.createElement('div');
            el.id = `indicator-${index}`;
            el.className = 'indicator text-center p-2 rounded-md flex-shrink-0 bg-gray-700/50';
            el.textContent = chord.split('_')[0];
            progressionDisplay.appendChild(el);
        });
    }

    function updateNoteDisplay(notes) {
        if (noteDisplayArea) noteDisplayArea.textContent = (!notes || notes.length === 0) ? '...' : notes.map(n => Chord.midiToNoteName(n.pitch)).join(' ');
    }

    function animatePlayhead() {
        if (!isPlaying) { animationFrameId = null; return; }
        const totalTicks = progression.length * TICKS_PER_MEASURE;
        if (totalTicks > 0) {
            const currentTransportTicks = Tone.Transport.ticks;

            if (playhead) {
                const currentLoopTicks = currentTransportTicks % totalTicks;
                playhead.style.left = `${(currentLoopTicks / totalTicks) * 100}%`;
            }

            if (activeLeadNoteInfo) {
                const { pitch, startTicks, element, colorStops } = activeLeadNoteInfo;
                const durationTicks = Math.max(0, currentTransportTicks - startTicks);
                const startLoopTicks = startTicks % totalTicks;

                if (startLoopTicks + durationTicks > totalTicks) {
                    // --- ループをまたぐ場合の処理 ---
                    const width1_ticks = totalTicks - startLoopTicks;
                    element.style.width = `${Math.max(0.5, (width1_ticks / totalTicks) * 100)}%`;
                    updateNoteGradient(element, startTicks, durationTicks, colorStops);

                    if (!activeLeadNoteInfo.element2) {
                        const nextLoopStartTicks = Math.floor(startTicks / totalTicks) * totalTicks + totalTicks;
                        const newElement2 = drawPlayedNote(pitch, nextLoopStartTicks);
                        if (newElement2) {
                            activeLeadNoteInfo.element2 = newElement2;
                        }
                    }

                    if (activeLeadNoteInfo.element2) {
                        const width2_ticks = durationTicks - width1_ticks;
                        activeLeadNoteInfo.element2.style.width = `${Math.max(0.5, (width2_ticks / totalTicks) * 100)}%`;
                        activeLeadNoteInfo.element2.style.background = element.style.background;
                    }
                } else {
                    // --- ループをまたがない場合の処理 ---
                    const widthPercentage = (durationTicks / totalTicks) * 100;
                    element.style.width = `${Math.max(0.5, widthPercentage)}%`;
                    updateNoteGradient(element, startTicks, durationTicks, colorStops);
                    if (activeLeadNoteInfo.element2) {
                        activeLeadNoteInfo.element2.style.width = '0%';
                    }
                }
            }
        }
        animationFrameId = requestAnimationFrame(animatePlayhead);
    }

    function setupKeyboardListener() {
        const isPlayKey = (e) => e.code === 'Space' || e.code.startsWith('Digit') || e.code.startsWith('Numpad');
        document.addEventListener('keydown', (e) => {
            if (['INPUT', 'SELECT'].includes(e.target.tagName) || !isPlayKey(e) || activeKeys.has(e.code)) return;
            e.preventDefault();
            activeKeys.add(e.code);
            if (activeKeys.size === 1) handleMidiNoteOn(0.75, 'keyboard');
        });
        document.addEventListener('keyup', (e) => {
            if (['INPUT', 'SELECT'].includes(e.target.tagName) || !isPlayKey(e)) return;
            activeKeys.delete(e.code);
            if (activeKeys.size === 0) handleMidiNoteOff('keyboard');
        });
    }

    function handleMidiNoteOn(velocity = 0.75, source = 'unknown') {
        if (source !== 'button') { // ボタンの押下はトラッキングしない
            sessionAnalytics.velocities.push(velocity);
            sessionAnalytics.noteOnCount++;
        }

        if (mainContainer) {
            mainContainer.classList.add('feedback-glow');
            setTimeout(() => mainContainer.classList.remove('feedback-glow'), 500);
        }

        if (midiKeyDownCount === 0 && playNoteButton) {
            playNoteButton.style.backgroundColor = '';
            playNoteButton.classList.remove('bg-indigo-600', 'hover:bg-indigo-700');
            playNoteButton.classList.add('bg-purple-500');
        }
       
        if (source === 'midi') {
            midiKeyDownCount++;
            playNextLeadNote(velocity);
        } else {
            if (++midiKeyDownCount === 1) playNextLeadNote(velocity);
        }
    }

    function handleMidiNoteOff(source = 'unknown') {
        // PCキーボードとUIボタンはカウンタで厳密に管理
        if (source === 'keyboard' || source === 'button') {
            if (midiKeyDownCount > 0 && --midiKeyDownCount === 0) {
                stopCurrentLeadNote();
                if(playNoteButton) {
                    playNoteButton.style.backgroundColor = '';
                    playNoteButton.classList.remove('bg-purple-500');
                    playNoteButton.classList.add('bg-indigo-600', 'hover:bg-indigo-700');
                }
            }
            return;
        }

        // MIDI入力はNote Off信号の欠落に弱いため、より強力に音を停止する
        if (source === 'midi') {
            stopCurrentLeadNote();
            midiKeyDownCount = 0; // カウンタを強制リセット
            if(playNoteButton) {
                playNoteButton.style.backgroundColor = '';
                playNoteButton.classList.remove('bg-purple-500');
                playNoteButton.classList.add('bg-indigo-600', 'hover:bg-indigo-700');
            }
        }
    }

    function handleMidiChannelAftertouch(value) { // value is 0.0 ~ 1.0
        sessionAnalytics.aftertouchValues.push(value);
        sessionAnalytics.aftertouchCount++;
        let newColorRgbString = null;

        if (midiKeyDownCount > 0) {
            if (leadSynth) {
                const now = Tone.now();
                const timeConstant = 0.02;

                const easedValue = Math.pow(value, 1.5);
               
                const newFrequency = 800 + (6200 * easedValue);
                leadSynth.filter.frequency.setTargetAtTime(newFrequency, now, timeConstant);

                // MODIFIED: 最小音量を-12dBに変更
                const newVolume = -12 + (12 * easedValue);
                leadSynth.volume.setTargetAtTime(newVolume, now, timeConstant);
            }

            const hue = 260;
            const saturation = 100 - (80 * value);
            const brightness = 80;
            const [r, g, b] = hsvToRgb(hue / 360, saturation / 100, brightness / 100);
            newColorRgbString = `rgb(${r}, ${g}, ${b})`;

            if(playNoteButton) {
                playNoteButton.classList.remove('bg-indigo-600', 'hover:bg-indigo-700', 'bg-purple-500');
                playNoteButton.style.backgroundColor = newColorRgbString;
            }
        }

        if (activeLeadNoteInfo && activeLeadNoteInfo.element && newColorRgbString) {
            activeLeadNoteInfo.colorStops.push({
                ticks: Tone.Transport.ticks,
                color: newColorRgbString
            });
        }
    }

    function sendSessionAnalytics() {
        if (sessionAnalytics.noteOnCount === 0 && sessionAnalytics.aftertouchCount === 0) {
            return;
        }

        const calculateStats = (arr) => {
            if (arr.length === 0) return { min: 0, q1: 0, median: 0, mean: 0, q3: 0, max: 0 };
            const sorted = [...arr].sort((a, b) => a - b);
            const sum = arr.reduce((a, b) => a + b, 0);
            return {
                min: parseFloat(sorted[0].toFixed(2)),
                q1: parseFloat(sorted[Math.floor(sorted.length / 4)].toFixed(2)),
                median: parseFloat(sorted[Math.floor(sorted.length / 2)].toFixed(2)),
                mean: parseFloat((sum / arr.length).toFixed(2)),
                q3: parseFloat(sorted[Math.floor(sorted.length * 3 / 4)].toFixed(2)),
                max: parseFloat(sorted[sorted.length - 1].toFixed(2)),
            };
        };

        const velocityStats = calculateStats(sessionAnalytics.velocities);
        const aftertouchStats = calculateStats(sessionAnalytics.aftertouchValues);

        trackEvent('play_session_summary', {
            note_on_count: sessionAnalytics.noteOnCount,
            aftertouch_count: sessionAnalytics.aftertouchCount,
            velocity_min: velocityStats.min,
            velocity_q1: velocityStats.q1,
            velocity_median: velocityStats.median,
            velocity_mean: velocityStats.mean,
            velocity_q3: velocityStats.q3,
            velocity_max: velocityStats.max,
            aftertouch_min: aftertouchStats.min,
            aftertouch_q1: aftertouchStats.q1,
            aftertouch_median: aftertouchStats.median,
            aftertouch_mean: aftertouchStats.mean,
            aftertouch_q3: aftertouchStats.q3,
            aftertouch_max: aftertouchStats.max
        });
    }


    function updateNoteGradient(element, startTicks, durationTicks, colorStops) {
        if (!element || durationTicks <= 0 || colorStops.length === 0) return;

        if (colorStops.length === 1) {
            element.style.background = colorStops[0].color;
            return;
        }

        const gradientStops = colorStops.map(stop => {
            const relativeTicks = stop.ticks - startTicks;
            const percentage = Math.max(0, Math.min(100, (relativeTicks / durationTicks) * 100));
            return `${stop.color} ${percentage}%`;
        }).join(', ');

        element.style.background = `linear-gradient(to right, ${gradientStops})`;
    }

    function attachMidiListeners(inputId) {
        if (currentMidiInput) {
            currentMidiInput.removeListener();
        }
        currentMidiInput = WebMidi.getInputById(inputId);
        if (currentMidiInput) {
            currentMidiInput.on("noteon", e => handleMidiNoteOn(e.velocity, 'midi'));
            currentMidiInput.on("noteoff", e => handleMidiNoteOff('midi'));
            currentMidiInput.on("channelaftertouch", e => handleMidiChannelAftertouch(e.value));
            currentMidiInput.on('controlchange', e => {
                if (e.controller.number === 123) {
                    console.warn('All Notes Off message received. Forcibly stopping sound.');
                    if (activeLeadNoteInfo) stopCurrentLeadNote();
                    if (midiKeyDownCount > 0) {
                        midiKeyDownCount = 0;
                        if(playNoteButton) {
                            playNoteButton.style.backgroundColor = '';
                            playNoteButton.classList.remove('bg-purple-500');
                            playNoteButton.classList.add('bg-indigo-600', 'hover:bg-indigo-700');
                        }
                    }
                }
            });
        } else {
             if(statusArea) statusArea.textContent = 'MIDIデバイス未接続。PCのキーボードで演奏できます。';
        }
    }

    function populateMidiDeviceList() {
        if (!midiInputSelect) return;
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
            if (stillExists) midiInputSelect.value = previouslySelectedId;
            attachMidiListeners(midiInputSelect.value);
        } else {
            midiInputSelect.innerHTML = '<option>利用可能なデバイスがありません</option>';
            if(currentMidiInput) attachMidiListeners(null);
            else if(statusArea) statusArea.textContent = 'MIDIデバイス未接続。PCのキーボードで演奏できます。';
        }
    }

    async function setupMidi() {
        if (typeof WebMidi === 'undefined' || !navigator.requestMIDIAccess) {
            if(settingsButton) settingsButton.style.display = 'none';
            return;
        }
        try {
            await WebMidi.enable();
            populateMidiDeviceList();
            if(midiInputSelect) midiInputSelect.addEventListener('change', (e) => {
                const selectedDeviceName = e.target.options[e.target.selectedIndex].text;
                attachMidiListeners(e.target.value);
                trackEvent('select_midi_device', {
                    device_name: selectedDeviceName
                });
            });
            WebMidi.addListener("connected", () => populateMidiDeviceList());
            WebMidi.addListener("disconnected", () => populateMidiDeviceList());
        } catch (err) {
            trackEvent('midi_error', { error_message: err.message });
            console.error("Could not enable MIDI:", err);
            if(statusArea) statusArea.textContent = 'MIDIデバイスの有効化に失敗しました。';
            if(midiInputSelect) midiInputSelect.innerHTML = '<option>MIDIの有効化に失敗</option>';
            if(settingsButton) settingsButton.style.display = 'none';
        }
    }

    async function ensureAudioContext() {
        if (Tone.context.state !== 'running') await Tone.start();
    }
});
