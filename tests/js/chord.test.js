// The Chord class is copied here from static/main.js to make it testable.
// In a real-world scenario, this class should be in its own module.
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
        if (quality.includes('(')) {
            quality = quality.substring(0, quality.indexOf('('));
        }
        if (quality.toLowerCase() === 'maj7') quality = 'M7';
        if (quality.toLowerCase() === 'min7') quality = 'm7';
        const useFlats = rootStr.includes('b');
        const notes = useFlats ? this.NOTES_FLAT : this.NOTES;
        let rootMidi = notes.indexOf(rootStr.charAt(0).toUpperCase() + rootStr.slice(1));
        if (rootMidi === -1) {
            const sharpIndex = this.NOTES.indexOf(rootStr.charAt(0).toUpperCase() + rootStr.slice(1));
            const flatIndex = this.NOTES_FLAT.indexOf(rootStr.charAt(0).toUpperCase() + rootStr.slice(1));
            rootMidi = sharpIndex !== -1 ? sharpIndex : flatIndex;
        }
        if (rootMidi === -1) return [];
        rootMidi += 48; // Start from C3
        const intervals = this.INTERVALS[quality] || this.INTERVALS[''];
        if (!intervals) return [];
        return intervals.map(interval => this.midiToNoteName(rootMidi + interval, useFlats));
    }
}


describe('Chord', () => {
    describe('midiToNoteName', () => {
        test('should convert MIDI number to note name (sharps)', () => {
            expect(Chord.midiToNoteName(60)).toBe('C4');
            expect(Chord.midiToNoteName(61)).toBe('C#4');
            expect(Chord.midiToNoteName(72)).toBe('C5');
        });

        test('should convert MIDI number to note name (flats)', () => {
            expect(Chord.midiToNoteName(61, true)).toBe('Db4');
            expect(Chord.midiToNoteName(63, true)).toBe('Eb4');
        });
    });

    describe('getVoicing', () => {
        test('should return correct voicing for major chords', () => {
            expect(Chord.getVoicing('C')).toEqual(['C3', 'E3', 'G3']);
            expect(Chord.getVoicing('G')).toEqual(['G3', 'B3', 'D4']);
        });

        test('should return correct voicing for minor chords', () => {
            expect(Chord.getVoicing('Am')).toEqual(['A3', 'C4', 'E4']);
        });

        test('should return correct voicing for dominant 7th chords', () => {
            expect(Chord.getVoicing('G7')).toEqual(['G3', 'B3', 'D4', 'F4']);
        });

        test('should return correct voicing for major 7th chords', () => {
            expect(Chord.getVoicing('Cmaj7')).toEqual(['C3', 'E3', 'G3', 'B3']);
        });

        test('should handle flat chords', () => {
            expect(Chord.getVoicing('Bb7')).toEqual(['Bb3', 'D4', 'F4', 'Ab4']);
        });

        test('should handle sharp chords', () => {
            expect(Chord.getVoicing('F#m7')).toEqual(['F#3', 'A3', 'C#4', 'E4']);
        });

        test('should return empty array for unknown chord', () => {
            expect(Chord.getVoicing('Unknown')).toEqual([]);
        });

        test('should handle complex chord names with parentheses', () => {
            expect(Chord.getVoicing('Cmaj7(9)')).toEqual(['C3', 'E3', 'G3', 'B3']);
        });
    });
});
