// DOMが完全に読み込まれたら処理を開始します
document.addEventListener('DOMContentLoaded', () => {
    // HTMLから操作したい要素を取得します
    const chordSelect = document.getElementById('chord-progression');
    const styleSelect = document.getElementById('music-style');
    const generateButton = document.getElementById('generate-button');
    const midiOutput = document.getElementById('midi-output');

    // Tone.jsのシンセサイザーを準備します
    const synth = new Tone.PolySynth(Tone.Synth).toDestination();

    // 「メロディ生成」ボタンがクリックされたときの処理を定義します
    generateButton.addEventListener('click', async () => {
        const chordProgression = chordSelect.value;
        const musicStyle = styleSelect.value;

        generateButton.textContent = '生成中...';
        generateButton.disabled = true;
        midiOutput.textContent = 'AIがメロディを考えています...';

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chord_progression: chordProgression,
                    style: musicStyle,
                }),
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const decodedMidi = atob(data.midi_data);
            midiOutput.textContent = decodedMidi;

            // --- メロディ再生ロジック ---
            // 以前の単音再生の代わりに、シーケンスを再生する処理を追加します。
            
            // 1. 再生中のシーケンスがあれば停止・クリアします
            Tone.Transport.stop();
            Tone.Transport.cancel();

            // 2. テキストデータをノート情報の配列に変換します
            //    各行は "pitch duration wait velocity instrument" の形式です
            const notes = decodedMidi.trim().split('\n').map(line => {
                const [pitch, duration, wait, velocity] = line.split(' ').map(Number);
                return { pitch, duration, wait, velocity };
            });

            // 3. Tone.jsのPartを使ってシーケンスをスケジューリングします
            let accumulatedTime = 0; // 経過時間を記録する変数 (ミリ秒)
            const part = new Tone.Part((time, note) => {
                // MIDIノート番号を周波数に変換
                const freq = Tone.Midi(note.pitch).toFrequency();
                // durationを秒に変換
                const dur = note.duration / 1000;
                // velocity(0-127)を音量(0-1)に変換
                const vel = note.velocity / 127;
                
                synth.triggerAttackRelease(freq, dur, time, vel);
            }, notes.map(note => {
                // 各ノートの開始時間を計算
                accumulatedTime += note.wait;
                const startTime = accumulatedTime / 1000; // 秒に変換
                return { time: startTime, ...note }; // Partに渡すオブジェクト
            })).start(0);

            // 4. オーディオを開始し、シーケンスの再生を開始します
            await Tone.start();
            Tone.Transport.start();

        } catch (error) {
            console.error('Error generating melody:', error);
            midiOutput.textContent = `エラーが発生しました: ${error.message}`;
        } finally {
            generateButton.textContent = 'メロディ生成';
            generateButton.disabled = false;
        }
    });
});

