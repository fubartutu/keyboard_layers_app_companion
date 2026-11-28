import configparser
import os
import sys


class Config:
    _config_file = "config.ini"
    # Optional, gitignored: per-machine overrides (e.g. [KEYMAP] path), read after config.ini
    _local_config_file = "config.local.ini"
    _config = None

    @staticmethod
    def __init__():
        if Config._config is not None:
            return
        print("Loading configuration...")
        Config._config = configparser.ConfigParser()
        try:
            read = Config._config.read([Config._config_file, Config._local_config_file])
            if Config._local_config_file in read:
                print(f"Using overrides from {Config._local_config_file}")
        except configparser.Error as e:
            print(f"Error reading configuration file: {e}")
            sys.exit(2)

        if "KEYBOARD_USB_HID" in Config._config:
            keyboard = Config._config["KEYBOARD_USB_HID"]
            Config.usage_page = int(keyboard.get("usage_page", "0xFF60"), 16)
            Config.usage = int(keyboard.get("usage", "0x61"), 16)
            # Optional: only use the keyboard whose HID product string is this (e.g. the
            # ZMK_KEYBOARD_NAME), when another keyboard also exposes the raw HID interface
            Config.product = keyboard.get("product", "").strip() or None

        if "KEYBOARD_BLE_HID" in Config._config:
            keyboard = Config._config["KEYBOARD_BLE_HID"]
            Config.vendor_id = int(keyboard.get("vendor_id", "0xFEED"), 16)
            Config.product_id = int(keyboard.get("product_id", "0x6000"), 16)

        if (
            "KEYBOARD_USB_HID" not in Config._config
            and "KEYBOARD_BLE_HID" not in Config._config
        ):
            print(
                f"\n\n\nNeither KEYBOARD_BLE_HID or KEYBOARD_USB_HID section found in config file: {Config._config_file}\n\n\n"
            )
            sys.exit(2)

        # Live keymap view: path to a ZMK .keymap file. Without it the web page shows layer images.
        Config.keymap = None
        Config.keymap_ref = None
        if "KEYMAP" in Config._config:
            # Optional git branch/tag/commit to read the keymap from (e.g. the flashed one)
            Config.keymap_ref = Config._config["KEYMAP"].get("ref", "").strip() or None
            path = Config._config["KEYMAP"].get("path", "").strip()
            if path:
                Config.keymap = os.path.expanduser(path)
                if not os.path.isfile(Config.keymap):
                    print(f"Keymap file not found: {Config.keymap} - falling back to layer images")
                    Config.keymap = None

        # ZSA Voyager: the Oryx layout to draw while it's the keyboard in use
        Config.oryx_layout = None
        Config.oryx_revision = "latest"
        Config.oryx_geometry = "voyager"
        if "ORYX" in Config._config:
            oryx = Config._config["ORYX"]
            Config.oryx_layout = oryx.get("layout", "").strip() or None
            Config.oryx_revision = oryx.get("revision", "").strip() or "latest"
            Config.oryx_geometry = oryx.get("geometry", "").strip() or "voyager"

        if "LAYER_IMAGES" in Config._config:
            values = Config._config["LAYER_IMAGES"].values()
            Config.layers = [v for v in values]
        else:
            print(
                f"LAYER_IMAGES section not found in config file: {Config._config_file}"
            )
            exit(2)
