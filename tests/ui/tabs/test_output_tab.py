from unittest.mock import patch, ANY, MagicMock

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QDir, QPoint

from ui.tabs.output_tab import OutputTab
from core.oxipng_level import DEFAULT_OXIPNG_LEVEL

@pytest.fixture
def app(qtbot):
    with (
        patch("ui.tabs.output_tab.WidgetManager.loadState"),
        patch("ui.tabs.output_tab.WidgetManager.saveState"),
    ):
        tab = OutputTab(
            {
                "disable_delete_startup": False,
                "enable_jxl_effort_10": False,
                "enable_quality_precision_snapping": False,
                "jpg_encoder": "JPEGLI",
                "png_encoder": "Oxipng",
                "jxl_lossy_modular": False,
                "jxl_int_effort": False,
                "avif_encoder": "AOM AV1",
            }
        )
        qtbot.addWidget(tab)
        return tab

def test_initial_state(app):
    # Format
    settings = app.getSettings()
    assert settings["format"] == "JPEG XL"
    assert settings["quality"] == 80
    assert settings["lossless"] == False
    assert settings["max_compression"] == False
    assert settings["effort"] == 7
    assert settings["intelligent_effort"] == False
    assert settings["jxl_modular"] == False
    assert settings["jxl_png_fallback"] == False
    assert settings["delete_original"] == False
    assert settings["jxl_verify"] == False
    assert settings["jxl_normalize_enable"] == False
    assert settings["jxl_normalize_when"] == "On Fail"
    assert not app.smIsFormatPoolEmpty()

    # Conv.
    assert settings["if_file_exists"] == "Rename"
    
    # After conv.
    assert not app.isClearAfterConvChecked()
    assert settings["delete_original_mode"] == "To Trash"

    # Save To
    assert settings["custom_output_dir"] == False
    assert settings["custom_output_dir_path"] == ""
    assert settings["keep_dir_struct"] == False

def test_thread_slider_change(app, qtbot):
    qtbot.mouseClick(app.threads_sl, Qt.LeftButton, pos=app.threads_sl.rect().center())
    assert app.threads_sb.value() == app.threads_sl.value()

def test_thread_spinbox_change(app):
    app.threads_sb.setValue(2)
    assert app.threads_sb.value() == 2
    assert app.threads_sb.value() == app.threads_sl.value()

def test_thread_slider_change(app):
    app.quality_sl.setValue(50)
    assert app.quality_sl.value() == 50
    assert app.quality_sl.value() == app.quality_sb.value()

def test_thread_spinbox_change(app):
    app.quality_sb.setValue(50)
    assert app.quality_sb.value() == 50
    assert app.quality_sl.value() == app.quality_sb.value()

def test_deleteOriginal_change(app):
    app.delete_original_cb.setChecked(True)
    assert app.delete_original_cmb.isEnabled()

def test_output_toggled(app):
    app.choose_output_ct_rb.setChecked(True)
    assert app.choose_output_ct_le.isEnabled()
    assert app.choose_output_ct_btn.isEnabled()
    
    app.choose_output_src_rb.setChecked(True)
    assert not app.choose_output_ct_le.isEnabled()
    assert not app.choose_output_ct_btn.isEnabled()

def test__onEffortToggled_jpeg_xl(app):
    app.jxl_int_effort_visible = True
    with (
        patch.object(app.format_cmb, "currentText", return_value="JPEG XL"),
        patch.object(app.int_effort_cb, "isChecked", return_value=True),
        patch.object(app.effort_sb, "setEnabled") as mock_setEnabled,
    ):
        app._onEffortToggled()
        mock_setEnabled.assert_called_once_with(False)

def test__onEffortToggled_other(app):
    app.jxl_int_effort_visible = True
    with (
        patch.object(app.format_cmb, "currentText", return_value="PNG"),
        patch.object(app.effort_sb, "setEnabled") as mock_setEnabled,
    ):
        app._onEffortToggled()
        mock_setEnabled.assert_called_once_with(True)

@pytest.mark.parametrize("visible", [True, False])
def test_onJXLLossyModularVisibleToggled(visible, app):
    with (
        patch.object(app.format_cmb, "currentText", return_value="JPEG XL"),
        patch("ui.tabs.output_tab.WidgetManager.setVisibleByTag") as mock_setVisibleByTag,
    ):
        app.onJXLLossyModularVisibleToggled(visible)

        assert app.jxl_lossy_modular_visible == visible
        mock_setVisibleByTag.assert_called_once_with("jxl_losssy_modular", visible)

@pytest.mark.parametrize("visible", [True, False])
def test_onJXLIntEffortVisibleToggled(visible, app):
    with (
        patch.object(app.format_cmb, "currentText", return_value="JPEG XL"),
        patch.object(app.int_effort_cb, "setVisible") as mock_setVisible,
        patch.object(app, "_onEffortToggled") as mock__onEffortToggled,
    ):
        app.onJXLIntEffortVisibleToggled(visible)

        assert app.jxl_int_effort_visible == visible
        mock_setVisible.assert_called_once_with(visible)
        mock__onEffortToggled.assert_called_once()

def test_onFormatChange_int_e_toggle(app):
    app.format_cmb.setCurrentText("JPEG XL")
    app.onJXLIntEffortVisibleToggled(True)
    app.int_effort_cb.setChecked(True)

    assert not app.effort_sb.isEnabled()

def test_onFormatChange_lossless_toggled(app):
    app.lossless_cb.setChecked(True)
    
    assert app.lossless_cb.isEnabled()
    assert not app.quality_sl.isEnabled()
    assert not app.quality_sb.isEnabled()
    
    app.lossless_cb.setChecked(False)
    
    assert app.lossless_cb.isEnabled()
    assert app.quality_sl.isEnabled()
    assert app.quality_sb.isEnabled()

@pytest.mark.parametrize("file_format, visible_widgets", [
    ("JPEG XL", ["quality", "effort", "lossless"]),
    ("AVIF", ["quality", "effort", "chroma_subsampling"]),
    ("WebP", ["quality", "effort", "lossless"]),
    ("JPEG", ["quality", "chroma_subsampling"]),
    ("PNG", ["quality", "lossless", "effort"]),
    ("Lossless JPEG Transcoding", ["effort", "jxl_verify", "jxl_normalize"]),
    ("JPEG Reconstruction", ["png_fallback"]),
    ("Smallest Lossless", ["smallest_lossless"]),
    ("Same Format", ["effort"]),
])
def test_onFormatChange_visibility(app, file_format, visible_widgets):
    app.format_cmb.setCurrentText(file_format)
    assert app.format_cmb.currentText() == file_format
    
    # Effort
    effort = "effort" in visible_widgets
    assert app.int_effort_cb.isVisibleTo(app) == ("int_effort" in visible_widgets)
    assert app.effort_sb.isVisibleTo(app) == effort
    assert app.effort_l.isVisibleTo(app) == effort
    
    # Quality
    quality = "quality" in visible_widgets
    assert app.quality_l.isVisibleTo(app) == quality
    assert app.quality_sl.isVisibleTo(app) == quality
    assert app.quality_sb.isVisibleTo(app) == quality
    
    # Lossless
    assert app.lossless_cb.isVisibleTo(app) == ("lossless" in visible_widgets)
    
    # Misc.
    jxl_modular = "jxl_modular" in visible_widgets
    assert app.jxl_modular_cb.isVisibleTo(app) == jxl_modular

    chroma_subsampling = "chroma_subsampling" in visible_widgets
    assert app.chroma_subsampling_l.isVisibleTo(app) == chroma_subsampling
    assert (
        app.chroma_subsampling_jpegli_cmb.isVisibleTo(app) == chroma_subsampling or
        app.chroma_subsampling_jpg_cmb.isVisibleTo(app) == chroma_subsampling or
        file_format == "AVIF"   # Tested in test_AVIF_chroma_subsampling_visibility
    )

    smallest_lossless = "smallest_lossless" in visible_widgets
    assert app.smallest_lossless_png_cb.isVisibleTo(app) == smallest_lossless
    assert app.smallest_lossless_webp_cb.isVisibleTo(app) == smallest_lossless
    assert app.smallest_lossless_jxl_cb.isVisibleTo(app) == smallest_lossless
    assert app.max_compression_cb.isVisibleTo(app) == smallest_lossless
    assert app.jxl_png_fallback_cb.isVisibleTo(app) == ("png_fallback" in visible_widgets)

    assert app.jxl_verify_cb.isVisibleTo(app) == ("jxl_verify" in visible_widgets)
    assert app.jxl_normalize_enable_cb.isVisibleTo(app) == ("jxl_normalize" in visible_widgets)
    assert app.jxl_normalize_when_cmb.isVisibleTo(app) == ("jxl_normalize" in visible_widgets)

def test_onFormatChange_same_format_route_visibility(app):
    app.format_cmb.setCurrentText("Same Format")
    assert app.sf_jpeg_route_l.isVisibleTo(app)
    assert app.sf_jpeg_route_cmb.isVisibleTo(app)

    app.format_cmb.setCurrentText("JPEG")
    assert not app.sf_jpeg_route_l.isVisibleTo(app)
    assert not app.sf_jpeg_route_cmb.isVisibleTo(app)

def test_getSettings_same_format_routes(app):
    app.format_cmb.setCurrentText("Same Format")
    app.sf_jpeg_route_cmb.setCurrentText("Lossless JPEG Transcoding")

    routes = app.getSettings()["same_format_routes"]

    # The single JPEG Route control must govern every JPEG_ALIASES entry,
    # not just jpg/jpeg - regression test for aliases silently falling back
    # to plain "JPEG" instead of the user's chosen route.
    assert routes["jpg"] == "Lossless JPEG Transcoding"
    assert routes["jpeg"] == "Lossless JPEG Transcoding"
    assert routes["jfif"] == "Lossless JPEG Transcoding"
    assert routes["jif"] == "Lossless JPEG Transcoding"
    assert routes["jpe"] == "Lossless JPEG Transcoding"

@pytest.mark.parametrize("encoder", [
    ("AOM AV1"),
    ("SVT-AV1-PSY"),
])
def test_AVIF_chroma_subsampling_visibility(encoder, app):
    app.format_cmb.setCurrentText("AVIF")
    app.onAVIFEncoderChanged(encoder)
    assert app.chroma_subsampling_svt_av1_psy_cmb.isVisibleTo(app) == (encoder == "SVT-AV1-PSY")
    assert app.chroma_subsampling_aom_av1_cmb.isVisibleTo(app) == (encoder == "AOM AV1")

@pytest.mark.parametrize("widget_name, variable_name", [
    ("int_effort_cb", "jxl_int_effort_visible"),
    ("jxl_modular_cb", "jxl_lossy_modular_visible"),
])
def test_onFormatChange_visibility_controled_by_vars(widget_name, variable_name, app):
    if not hasattr(app, variable_name):
        raise AssertionError(f"Variable \"{variable_name}\" does not exist")
    setattr(app, variable_name, False)
    app._onFormatChange()
    assert not getattr(app, widget_name).isVisibleTo(app), f"Widget \"{widget_name}\" does not exist"
    setattr(app, variable_name, True)
    app._onFormatChange()
    assert getattr(app, widget_name).isVisibleTo(app), f"Widget \"{widget_name}\" does not exist"

def test_onFormatChange_lossless_glitch(app):
    """Tests if an option set in one format affects others."""
    app.lossless_cb.setChecked(True)
    app.onJXLIntEffortVisibleToggled(True)
    assert not app.quality_sl.isEnabled()

    app.format_cmb.setCurrentText("WebP")
    assert app.quality_sl.isEnabled()

    app.format_cmb.setCurrentText("JPEG XL")
    
def test_onFormatChange_int_e_glitch(app):
    app.int_effort_cb.setChecked(True)
    app.onJXLIntEffortVisibleToggled(True)
    assert not app.effort_sb.isEnabled()

    app.format_cmb.setCurrentText("AVIF")
    assert app.effort_sb.isEnabled()

    app.format_cmb.setCurrentText("JPEG XL")
    assert not app.effort_sb.isEnabled()

def test_jpeg_xl_effort_10(app):
    app.format_cmb.setCurrentText("JPEG XL")
    
    assert app.effort_sb.maximum() == 9
    app.onJXLEffort10Enabled(True)
    assert app.effort_sb.maximum() == 10

@pytest.mark.parametrize("file_format, min_val, max_val", [
    ("JPEG XL", 1, 9),
    ("AVIF", 0, 10),
])
def test_effort_ranges(app, file_format, min_val, max_val):
    app.format_cmb.setCurrentText(file_format)
    
    assert app.effort_sb.minimum() == min_val
    assert app.effort_sb.maximum() == max_val

def test__chooseOutput_var_default(app):
    with (
        patch("ui.tabs.output_tab.QFileDialog") as mock_qfiledialog,
        patch("ui.lib.widget_manager.WidgetManager.getVar", return_value=None),
        patch("ui.lib.utils.isPathValidStr", return_value=False),
    ):
        mock_qfiledialog.return_value.exec.return_value = False

        app._chooseOutput()

        mock_qfiledialog.assert_called_once_with(app, ANY, QDir.homePath())

def test__chooseOutput_var_load(app):
    last_used = "/home/user/Pictures"
    with (
        patch("ui.tabs.output_tab.QFileDialog") as mock_qfiledialog,
        patch("ui.lib.widget_manager.WidgetManager.getVar", return_value=last_used),
        patch("ui.lib.widget_manager.WidgetManager.setVar") as mock_setVar,
        patch("ui.tabs.output_tab.isPathValidStr", return_value=True),
    ):
        mock_qfiledialog.return_value.exec.return_value = False

        app._chooseOutput()

        mock_qfiledialog.assert_called_once_with(app, ANY, last_used)

def test__chooseOutput_var_save(app):
    last_used = "/home/user/Pictures"
    with (
        patch("ui.tabs.output_tab.QFileDialog") as mock_qfiledialog,
        patch("ui.lib.widget_manager.WidgetManager.getVar", return_value=last_used),
        patch("ui.lib.widget_manager.WidgetManager.setVar") as mock_setVar,
        patch("ui.tabs.output_tab.isPathValidStr", return_value=False),
    ):
        mock_qfiledialog.return_value.exec.return_value = True
        mock_qfiledialog.return_value.directory.return_value.absolutePath.return_value = last_used
        app.choose_output_ct_le = MagicMock()

        app._chooseOutput()

        mock_setVar.assert_called_once_with("choose_output_last_dir", last_used)

@pytest.mark.parametrize("widget_name, variable_name, associated_key", [
    ("int_effort_cb", "jxl_int_effort_visible", "intelligent_effort"),
    ("jxl_modular_cb", "jxl_lossy_modular_visible", "jxl_modular"),
    ("int_effort_cb", "jxl_int_effort_visible", "intelligent_effort"),
])
def test_getSettings_widget_visibility(widget_name, variable_name, associated_key, app):
    getattr(app, widget_name).setChecked(True)
    setattr(app, variable_name, False)
    assert not app.getSettings()[associated_key]
    setattr(app, variable_name, True)
    assert app.getSettings()[associated_key]

def test_getSettings_no_png_opt(app):
    app.duplicates_cmb.setCurrentText("Rename")
    app.choose_output_src_rb.setChecked(True)
    app.delete_original_cb.setChecked(True)
    app.format_cmb.setCurrentText("JPEG")
    app.png_opt_inplace_cb.setChecked(True)

    settings = app.getSettings()

    assert settings["if_file_exists"] == "Rename"
    assert settings["custom_output_dir"] == False
    assert settings["delete_original"] == True

def test_getSettings_png_opt(app):
    app.duplicates_cmb.setCurrentText("Rename")
    app.choose_output_ct_rb.setChecked(False)
    app.delete_original_cb.setChecked(True)
    app.format_cmb.setCurrentText("PNG Optimization")
    app.png_opt_inplace_cb.setChecked(True)

    settings = app.getSettings()

    assert settings["if_file_exists"] == "Replace"
    assert settings["custom_output_dir"] == False
    assert settings["delete_original"] == False

@pytest.mark.parametrize(
    "jxl_modular_visible, jxl_lossless_checked, jxl_modular_checked, expected_return", [
        (False, False, True, False),
        (True, True, True, False),
        (False, True, True, False),
        (True, False, True, True),
    ]
)
def test_getSettings_jxl_lossy_modular(
    jxl_modular_visible,
    jxl_lossless_checked,
    jxl_modular_checked,
    expected_return,
    app,
):
    app.jxl_modular_cb.setChecked(True)
    setattr(app, "jxl_lossy_modular_visible", jxl_modular_visible)
    app.lossless_cb.setChecked(jxl_lossless_checked)
    app.jxl_modular_cb.setChecked(jxl_modular_checked)

    assert app.getSettings()["jxl_modular"] == expected_return

def test__onJXLNormalizeClicked_no_var(app):
    with (
        patch.object(app.wm, "getVar", return_value=None) as mock_getVar,
        patch.object(app.wm, "setVar") as mock_setVar,
        patch("ui.tabs.output_tab.message_box.info") as mock_message_box_info,
    ):
        app._onJXLNormalizeClicked()
    
    mock_getVar.assert_called_once_with("jxl_normalize_checksum_msg_seen")
    mock_message_box_info.assert_called_once()
    mock_setVar.assert_called_once_with("jxl_normalize_checksum_msg_seen", True)

def test__onJXLNormalizeClicked_var_present(app):
    with (
        patch.object(app.wm, "getVar", return_value=True) as mock_getVar,
        patch.object(app.wm, "setVar") as mock_setVar,
        patch("ui.tabs.output_tab.message_box.info") as mock_message_box_info,
    ):
        app._onJXLNormalizeClicked()
    
    mock_getVar.assert_called_once_with("jxl_normalize_checksum_msg_seen")
    mock_message_box_info.assert_not_called()
    mock_setVar.assert_not_called()

@pytest.mark.parametrize("encoder", ("AOM AV1", "SVT-AV1-PSY"))
def test_onAVIFEncoderChanged_happy_path(encoder, app):
    app.format_cmb.setCurrentText("AVIF")

    app.onAVIFEncoderChanged(encoder)

    assert app.chroma_subsampling_svt_av1_psy_cmb.isVisibleTo(app) == (encoder == "SVT-AV1-PSY")
    assert app.chroma_subsampling_aom_av1_cmb.isVisibleTo(app) == (encoder == "AOM AV1")

def test_onAVIFEncoderChanged_other_format(app):
    app.format_cmb.setCurrentText("JPEG XL")

    app.onAVIFEncoderChanged("AOM AV1")

    assert not app.chroma_subsampling_svt_av1_psy_cmb.isVisibleTo(app)
    assert not app.chroma_subsampling_aom_av1_cmb.isVisibleTo(app)

def test_onJPEGEncoderChanged_updates_state_and_rereads_on_format_change(app):
    app.format_cmb.setCurrentText("JPEG")
    assert app.chroma_subsampling_jpegli_cmb.isVisibleTo(app)
    assert not app.chroma_subsampling_jpg_cmb.isVisibleTo(app)

    # Encoder changed live while NOT on the JPEG format - state must be stored
    app.format_cmb.setCurrentText("JPEG XL")
    app.onJPEGEncoderChanged("libjpeg")
    assert app.jpg_encoder == "libjpeg"

    # Switching back must re-derive visibility from the updated value
    app.format_cmb.setCurrentText("JPEG")
    assert app.chroma_subsampling_jpg_cmb.isVisibleTo(app)
    assert not app.chroma_subsampling_jpegli_cmb.isVisibleTo(app)

@pytest.mark.parametrize("fmt", ("PNG",))
def test_resetToDefault_png_lossless_checked(app, fmt):
    app.format_cmb.setCurrentText(fmt)
    app.lossless_cb.setChecked(False)

    app.resetToDefault()

    assert app.lossless_cb.isChecked()

def test_onFormatChange_same_format_preset_visibility(app):
    app.format_cmb.setCurrentText("Same Format")
    assert app.sf_preset_l.isVisibleTo(app)
    assert app.sf_preset_cmb.isVisibleTo(app)
    assert not app.quality_sl.isVisibleTo(app)
    assert not app.quality_sb.isVisibleTo(app)
    assert not app.lossless_cb.isVisibleTo(app)

    app.format_cmb.setCurrentText("JPEG")
    assert not app.sf_preset_l.isVisibleTo(app)
    assert not app.sf_preset_cmb.isVisibleTo(app)

def test_same_format_advanced_visibility(app):
    app.format_cmb.setCurrentText("Same Format")
    assert not app.sf_png_q_sb.isVisibleTo(app)
    assert not app.sf_jxl_lossless_cb.isVisibleTo(app)
    assert not app.sf_avif_q_sb.isVisibleTo(app)

    app.sf_preset_cmb.setCurrentText("Custom")
    assert app.sf_png_q_sb.isVisibleTo(app)
    assert app.sf_png_lossless_cb.isVisibleTo(app)
    assert app.sf_jxl_q_sb.isVisibleTo(app)
    assert app.sf_webp_lossless_cb.isVisibleTo(app)
    assert app.sf_avif_q_sb.isVisibleTo(app)
    assert app.sf_jpeg_q_sb.isVisibleTo(app)

    app.sf_preset_cmb.setCurrentText("Quality")
    assert not app.sf_png_q_sb.isVisibleTo(app)

def test_same_format_advanced_hidden_outside_mode(app):
    app.sf_preset_cmb.setCurrentText("Custom")
    app.format_cmb.setCurrentText("JPEG XL")
    assert not app.sf_png_q_sb.isVisibleTo(app)

def test_getSettings_same_format_settings_preset(app):
    app.format_cmb.setCurrentText("Same Format")
    app.sf_preset_cmb.setCurrentText("Quality")

    settings = app.getSettings()["same_format_settings"]
    assert settings["PNG"] == {"lossless": True, "quality": 90}
    assert settings["JPEG XL"] == {"lossless": True, "quality": 90}
    assert settings["WebP"] == {"lossless": True, "quality": 90}
    assert settings["AVIF"] == {"lossless": False, "quality": 90}
    assert settings["JPEG"] == {"lossless": False, "quality": 90}

    app.sf_preset_cmb.setCurrentText("Small")
    settings = app.getSettings()["same_format_settings"]
    assert settings["AVIF"] == {"lossless": False, "quality": 70}
    assert settings["JPEG"] == {"lossless": False, "quality": 70}

def test_getSettings_same_format_settings_custom(app):
    app.format_cmb.setCurrentText("Same Format")
    app.sf_preset_cmb.setCurrentText("Custom")
    app.sf_png_lossless_cb.setChecked(False)
    app.sf_png_q_sb.setValue(75)
    app.sf_jxl_lossless_cb.setChecked(True)
    app.sf_jpeg_q_sb.setValue(65)

    settings = app.getSettings()["same_format_settings"]
    assert settings["PNG"] == {"lossless": False, "quality": 75}
    assert settings["JPEG XL"] == {"lossless": True, "quality": 90}
    assert settings["JPEG"] == {"lossless": False, "quality": 65}

def test_sf_preset_custom_seeds_from_previous(app):
    app.format_cmb.setCurrentText("Same Format")
    app.sf_preset_cmb.setCurrentText("Small")
    app.sf_preset_cmb.setCurrentText("Custom")

    assert app.sf_png_lossless_cb.isChecked() is False
    assert app.sf_png_q_sb.value() == 80
    assert app.sf_avif_q_sb.value() == 70
    assert app.sf_jpeg_q_sb.value() == 70

def test_sf_preset_custom_seed_does_not_overwrite_saved_on_restore(app):
    # Simulates startup restore: "Custom" selected with sf_prev_preset None
    # must not seed (saved per-format values survive).
    app.format_cmb.setCurrentText("Same Format")
    app.sf_png_q_sb.setValue(42)
    app.sf_prev_preset = None
    app.sf_preset_cmb.setCurrentText("Custom")

    assert app.sf_png_q_sb.value() == 42
def test_png_opt_inplace_happy_path(app):
    # PNG Optimization / inplace on
    app.format_cmb.setCurrentText("PNG Optimization")
    app.delete_original_cb.setChecked(False)
    app.png_opt_inplace_cb.setChecked(True)
    assert not app.output_grp.isEnabled()
    assert not app.duplicates_l.isEnabled()
    assert not app.duplicates_cmb.isEnabled()
    assert not app.delete_original_cb.isEnabled()
    assert not app.delete_original_cmb.isEnabled()

    # PNG Optimization / inplace off
    app.png_opt_inplace_cb.setChecked(False)
    assert app.output_grp.isEnabled()
    assert app.duplicates_l.isEnabled()
    assert app.duplicates_cmb.isEnabled()
    assert app.delete_original_cb.isEnabled()
    assert not app.delete_original_cmb.isEnabled()

    # JPEG / reference
    app.png_opt_inplace_cb.setChecked(True)
    app.format_cmb.setCurrentText("JPEG")
    assert app.output_grp.isEnabled()
    assert app.duplicates_l.isEnabled()
    assert app.duplicates_cmb.isEnabled()
    assert app.delete_original_cb.isEnabled()
    assert not app.delete_original_cmb.isEnabled()

def test_delete_original_happy_path(app):
    # Default behavior
    app.format_cmb.setCurrentText("JPEG")
    app.delete_original_cb.setChecked(True)
    assert app.delete_original_cmb.isEnabled()
    app.delete_original_cb.setChecked(False)
    assert not app.delete_original_cmb.isEnabled()

    # PNG Optimization
    app.format_cmb.setCurrentText("PNG Optimization")
    app.png_opt_inplace_cb.setChecked(True)
    assert not app.delete_original_cb.isEnabled()
    assert not app.delete_original_cmb.isEnabled()
    app.png_opt_inplace_cb.setChecked(False)
    app.delete_original_cb.setChecked(False)
    assert app.delete_original_cb.isEnabled()
    assert not app.delete_original_cmb.isEnabled()

    # Verify default behavior
    app.format_cmb.setCurrentText("JPEG")
    assert app.delete_original_cb.isEnabled()
    assert not app.delete_original_cmb.isEnabled()
    app.delete_original_cb.setChecked(True)
    assert app.delete_original_cb.isEnabled()
    assert app.delete_original_cmb.isEnabled()


def test_png_level_row_only_for_lossless_png(app):
    app.format_cmb.setCurrentText("PNG")
    assert app.lossless_cb.isChecked()
    assert app.effort_sb.isVisibleTo(app)
    assert app.effort_l.text() == "Level"
    assert app.effort_sb.maximum() == 9

    app.lossless_cb.setChecked(False)
    assert not app.effort_sb.isVisibleTo(app)

    app.lossless_cb.setChecked(True)
    app.onPNGEncoderChanged("Legacy (ImageMagick)")
    assert not app.effort_sb.isVisibleTo(app)

    app.onPNGEncoderChanged("Oxipng")
    app.format_cmb.setCurrentText("JPEG XL")
    assert app.effort_sb.isVisibleTo(app)
    assert app.effort_l.text() == "Effort"

def test_png_level_settings_and_per_format_memory(app):
    app.format_cmb.setCurrentText("PNG")
    app.effort_sb.setValue(6)
    assert app.getSettings()["png_level"] == 6

    app.format_cmb.setCurrentText("AVIF")
    app.format_cmb.setCurrentText("PNG")
    assert app.effort_sb.value() == 6

    app.format_cmb.setCurrentText("Same Format")
    assert app.getSettings()["png_level"] == DEFAULT_OXIPNG_LEVEL

def test_reset_to_defaults_restores_png_level(app):
    app.format_cmb.setCurrentText("PNG")
    app.effort_sb.setValue(8)
    app.resetToDefault()
    assert app.effort_sb.value() == DEFAULT_OXIPNG_LEVEL

def test_same_format_lossless_disables_quality(app):
    app.format_cmb.setCurrentText("Same Format")
    app.sf_preset_cmb.setCurrentText("Custom")
    app.sf_png_lossless_cb.setChecked(True)
    assert not app.sf_png_q_sb.isEnabled()

    app.sf_png_lossless_cb.setChecked(False)
    assert app.sf_png_q_sb.isEnabled()

def test_same_format_custom_rows_share_columns(app, qtbot):
    app.format_cmb.setCurrentText("Same Format")
    app.sf_preset_cmb.setCurrentText("Custom")
    app.resize(1040, 520)
    app.show()
    qtbot.waitExposed(app)

    def x_in_tab(widget):
        return widget.mapTo(app, QPoint(0, 0)).x()

    quality_spins = (app.sf_png_q_sb, app.sf_jxl_q_sb, app.sf_webp_q_sb, app.sf_avif_q_sb, app.sf_jpeg_q_sb)
    assert len({x_in_tab(w) for w in quality_spins}) == 1
    assert x_in_tab(app.effort_sb) == x_in_tab(app.sf_png_q_sb)
    assert x_in_tab(app.sf_preset_cmb) == x_in_tab(app.sf_png_q_sb)
    assert x_in_tab(app.sf_jpeg_route_cmb) == x_in_tab(app.sf_png_q_sb)


def test_same_format_custom_stays_clear_in_a_short_scroll_area(app, qtbot):
    from PySide6.QtWidgets import QWidget
    from ui.widgets.scroll_area import ScrollArea

    # Same as the main window: the Output tab sits in a ScrollArea, in a 320px-high window.
    scroll = ScrollArea()
    qtbot.addWidget(scroll)
    app.format_cmb.setCurrentText("Same Format")
    app.sf_preset_cmb.setCurrentText("Custom")
    scroll.setWidget(app)
    scroll.resize(703, 320)
    scroll.show()
    qtbot.waitExposed(scroll)

    group = app.format_grp
    assert group.height() >= group.sizeHint().height()
    rows = [w for w in group.children() if isinstance(w, QWidget) and w.isVisible()]
    for i, a in enumerate(rows):
        assert group.rect().contains(a.geometry())
        for b in rows[i + 1:]:
            assert not a.geometry().intersects(b.geometry())
    scroll.takeWidget()    # Hand the tab back, so its fixture can tear it down (the scroll area is deleted at teardown)

def test_height_limit_follows_content(app):
    app.format_cmb.setCurrentText("Same Format")
    app.sf_preset_cmb.setCurrentText("Custom")
    assert app.maximumHeight() == max(320, app.sizeHint().height())

    app.format_cmb.setCurrentText("JPEG XL")
    assert app.maximumHeight() == max(320, app.sizeHint().height())
