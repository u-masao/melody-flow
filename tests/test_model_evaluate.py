from unittest.mock import MagicMock, patch

import mido
import pytest
from src.model.evaluate import MelodyGenerator


@pytest.fixture
def mock_dependencies():
    """MelodyGeneratorの初期化に必要な依存関係をモック化するフィクスチャ"""
    return {
        "model": MagicMock(),
        "tokenizer": MagicMock(),
        "note_tokenizer_helper": MagicMock(),
        "device": "cpu",
    }


@pytest.fixture
def melody_generator(mock_dependencies):
    """テスト用のMelodyGeneratorインスタンスを生成するフィクスチャ"""
    return MelodyGenerator(**mock_dependencies)


@pytest.fixture
def sample_parsed_notes():
    """テスト用のサンプルノートデータを提供するフィクスチャ"""
    return [
        {"pitch": 60, "duration": 480, "wait": 0, "velocity": 100, "instrument": 0},
        {"pitch": 62, "duration": 480, "wait": 500, "velocity": 100, "instrument": 0},
    ]


@patch("src.model.evaluate.mido.MidiFile")
@patch("src.model.evaluate.mido.MidiTrack")
@patch("src.model.evaluate.FluidSynth")
@patch("src.model.evaluate.tempfile.NamedTemporaryFile")
@patch("src.model.evaluate.tempfile.mktemp")
@patch("src.model.evaluate.os.remove")
@patch("src.model.evaluate.os.path.exists", return_value=True)
def test_create_wav_from_notes_success(
    mock_exists,
    mock_remove,
    mock_mktemp,
    mock_tempfile,
    mock_fluidsynth,
    mock_miditrack,
    mock_midifile,
    melody_generator,
    sample_parsed_notes,
):
    """
    正常系テスト: _create_wav_from_notesが有効なノートリストからWAVファイルパスを返すことを確認
    """
    mock_mid_instance = MagicMock()
    mock_midifile.return_value = mock_mid_instance
    mock_track_instance = MagicMock()
    mock_miditrack.return_value = mock_track_instance
    mock_tracks_list = MagicMock()
    mock_mid_instance.tracks = mock_tracks_list
    mock_mid_file = MagicMock()
    mock_mid_file.name = "/tmp/fake_midi_file.mid"
    mock_tempfile.return_value.__enter__.return_value = mock_mid_file
    mock_mktemp.return_value = "/tmp/fake_wav_file.wav"
    mock_fs_instance = MagicMock()
    mock_fluidsynth.return_value = mock_fs_instance

    result_path = melody_generator._create_wav_from_notes(sample_parsed_notes)

    assert result_path == "/tmp/fake_wav_file.wav"
    mock_midifile.assert_called_once()
    mock_miditrack.assert_called_once()
    mock_tracks_list.append.assert_called_once_with(mock_track_instance)
    assert mock_track_instance.append.call_count == 6
    mock_track_instance.append.assert_any_call(
        mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120))
    )
    mock_track_instance.append.assert_any_call(mido.Message("program_change", program=0, time=0))
    mock_mid_instance.save.assert_called_once_with("/tmp/fake_midi_file.mid")
    mock_fluidsynth.assert_called_once()
    mock_fs_instance.midi_to_audio.assert_called_once_with(
        "/tmp/fake_midi_file.mid", "/tmp/fake_wav_file.wav"
    )
    mock_exists.assert_called_once_with("/tmp/fake_midi_file.mid")
    mock_remove.assert_called_once_with("/tmp/fake_midi_file.mid")


def test_create_wav_from_notes_empty_input(melody_generator):
    """
    境界系テスト: 空のノートリストが与えられた場合にNoneを返すことを確認
    """
    assert melody_generator._create_wav_from_notes([]) is None


@patch("src.model.evaluate.mido.MidiFile")
@patch("src.model.evaluate.mido.MidiTrack")
@patch("src.model.evaluate.FluidSynth")
@patch("src.model.evaluate.tempfile.NamedTemporaryFile")
@patch("src.model.evaluate.os.remove")
@patch("src.model.evaluate.os.path.exists", return_value=True)
def test_create_wav_from_notes_fluidsynth_error(
    mock_exists,
    mock_remove,
    mock_tempfile,
    mock_fluidsynth,
    mock_miditrack,
    mock_midifile,
    melody_generator,
    sample_parsed_notes,
):
    """
    異常系テスト: FluidSynthで例外が発生した場合にNoneを返し、
    ファイルをクリーンアップすることを確認
    """
    mock_mid_instance = MagicMock()
    mock_midifile.return_value = mock_mid_instance
    mock_track_instance = MagicMock()
    mock_miditrack.return_value = mock_track_instance
    mock_mid_instance.tracks = MagicMock()
    mock_mid_file = MagicMock()
    mock_mid_file.name = "/tmp/fake_midi_file.mid"
    mock_tempfile.return_value.__enter__.return_value = mock_mid_file
    mock_fs_instance = MagicMock()
    mock_fluidsynth.return_value = mock_fs_instance
    mock_fs_instance.midi_to_audio.side_effect = Exception("FluidSynth failed")

    result_path = melody_generator._create_wav_from_notes(sample_parsed_notes)

    assert result_path is None
    mock_fs_instance.midi_to_audio.assert_called_once()
    mock_exists.assert_called_once_with("/tmp/fake_midi_file.mid")
    mock_remove.assert_called_once_with("/tmp/fake_midi_file.mid")
