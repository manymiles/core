"""Media Player platform for the Uniden Scanner."""

from datetime import timedelta
from io import BytesIO
import logging
import socket
import time
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import parse
import requests

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    AddEntitiesCallback,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

SUPPORT_UNIDEN = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.TURN_OFF
)

refresh_time = 2
SCAN_INTERVAL = timedelta(seconds=refresh_time)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Uniden Scanner platform.

    This function is now deprecated and will be replaced by async_setup_entry.
    """
    _LOGGER.warning(
        "Uniden Scanner platform setup from configuration.yaml is deprecated"
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Uniden Scanner media player from a config entry."""

    # _LOGGER.warning(f"config_entry: {config_entry.data['Scanner IP Port']}")

    scanner_details = {
        "ip_address": config_entry.data["Scanner IP Address"],
        "port": config_entry.data["Scanner IP Port"],
        "name": config_entry.data["Scanner Name"],
        "model": config_entry.data["Scanner Model"],
        "enabled": config_entry.data["Active"],
        "access_method": config_entry.data["Access Method"],
    }

    async_add_entities([UnidenScanner(scanner_details)], True)


class UnidenScanner(MediaPlayerEntity):
    """Representation of a Uniden Scanner."""

    def __init__(self, scanner_details: dict) -> None:
        """Initialize the Uniden Scanner."""
        self._name = scanner_details["name"]
        self._ip_address = scanner_details["ip_address"]
        self._port = int(scanner_details["port"])
        self._model = scanner_details["model"]
        self._enabled = scanner_details["enabled"]
        self._access_method = scanner_details["access_method"]
        self._volume = 0
        self._state = MediaPlayerState.OFF
        self._reachable = False
        self._mode = "unknown"
        self._is_volume_muted = False
        self._unmute_volume = self._volume
        self._last_set_volume_time = 0.0
        self._media_title = "No Title"
        self._media_pos = 0
        self._media_duration = 0
        self._media_album_name = "Album Name"
        self._media_artist = "Artist Name"
        self.set_offline()

    @property
    def name(self) -> str:
        """Return the name of the scanner."""
        return self._name

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the scanner."""
        if self._mode == "Trunk Scan Hold":
            return MediaPlayerState.PAUSED
        if self._mode == "Trunk Scan":
            return MediaPlayerState.PLAYING
        if self._mode == "Scan Mode":
            return MediaPlayerState.PLAYING
        return MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def is_volume_muted(self) -> bool:
        """Boolean if volume is currently muted."""
        return self._is_volume_muted

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return the list of supported features."""
        return SUPPORT_UNIDEN

    @property
    def media_title(self) -> str | None:
        """Return the title of current playing media."""
        return self._media_title

    @property
    def media_content_type(self) -> str | None:
        """Return the content type of current playing media."""
        if self.state in [MediaPlayerState.PLAYING, MediaPlayerState.PAUSED]:
            return MediaType.MUSIC
        return MediaPlayerState.IDLE

    @property
    def media_artist(self) -> str | None:
        """Return the artist of current playing media, music track only."""
        return self._media_artist

    @property
    def media_album_name(self) -> str | None:
        """Return the album name of current playing media, music track only."""
        return self._media_album_name

    def get_xml_only(self, response: str) -> str:
        """Extracts and returns only the XML portion of a response string."""

        xml_start = response.find("<?xml")

        if xml_start != -1:
            return response[xml_start:]
        return ""

    def send_command(self, command: str, return_content) -> bytes | None:
        """Sends a command to the scanner via UDP and returns the response."""
        response = b""

        try:
            # Create a UDP socket
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(refresh_time - 0.25)  # 1 second timeout
                # Send the command with a carriage return
                cmd = (command + "\r").encode("latin-1")
                s.sendto(cmd, (self._ip_address, self._port))

                # Listen for a response
                data, addr = s.recvfrom(2048)

                if not self._reachable:
                    _LOGGER.info("%s is now reachable", self._name)

                self._reachable = True

                return data
        except TimeoutError:
            if self._reachable:
                # Only report this once so the logs don't get flooded
                _LOGGER.error("Timed out waiting for response from scanner")

            self._reachable = False

            return None
        except OSError:
            _LOGGER.error("UDP communication error")
            return None

        response = (
            response.replace("\n", "").replace("\r", "").replace("\xa0", " ").strip()
        )

        # _LOGGER.warning(f"Full response was: {response}")
        # If the caller wants XML only, extract that portion
        if return_content == "xml":
            response = self.get_xml_only(response)

        return response

    def update(self) -> None:
        """Fetch the latest state."""
        current_condition = {}

        # _LOGGER.warning("Update called: %s", self._reachable)

        if not self._enabled:
            # _LOGGER.warning("Not enabled: %s", self._name)
            self.set_offline()
            return

        match self._access_method:
            case "Direct":
                # _LOGGER.warning("Update called. REachable before: %s", self._reachable)
                current_condition = self.fetch_direct()

                # _LOGGER.warning("Update called. REachable after: %s", self._reachable)
            case "API":
                current_condition = self.fetch_api()
            case _:
                # Should not happen, but just in case
                _LOGGER.error("Unknown access method")
                # status = "unknown"

        if current_condition["error"] is None:
            self.set_online()
            self.update_ui(current_condition)
        else:
            # Error on fetch
            _LOGGER.error("Error fetching status: %s", current_condition["error"])
            self.set_offline()

    def fetch_direct(self) -> dict:
        """Fetch the latest state directly from the scanner."""
        # _LOGGER.warning(f"Direct for {self._ip_address}")

        try:
            response = self.send_command("GSI", "xml")
            # _LOGGER.info(f"scanner response was: {response}")

            # Get the channel information from the XML response
            if response:
                (channel, dept_name) = self.get_channel(response)
                error = None
            else:
                (channel, dept_name) = "Unknown Channel", "Unknown Department"
                error = "No response from scanner"
                # self.set_offline()
        except requests.exceptions.RequestException:
            _LOGGER.error("Error fetching status")
            error = "Exception fetching status"
            (channel, dept_name) = "Unknown Channel", "Unknown Department"

        return {
            "channel": channel,
            "dept_name": dept_name,
            "mode": "Trunk Scan",
            "volume": 5,
            "error": error,
        }

        # return current_condition

    def get_channel(self, response: bytes) -> tuple[str | None, str | None]:
        """Parse the XML response to extract the current channel and department."""
        # channel = ""

        # Extract the XML part from the response
        xml_start = response.find(b"<?xml")
        if xml_start == -1:
            return "Undetermined", ""

        xml_data = response[xml_start:]

        # Parse the XML
        tree = parse(BytesIO(xml_data))
        root = tree.getroot()

        # Find the Property element and get the Mute status
        property_elem = root.find(".//Property")
        if property_elem is None:
            return "Undetermined", ""

        mute_status = property_elem.get("Mute")

        if mute_status == "Mute":
            return "Scanning...", ""

        # Get Department name
        dept = root.find(".//Department")
        dept_name = dept.get("Name") if dept is not None else "Unknown Department"

        # Try to find either ConvFrequency or TGID element
        conv_freq = root.find(".//ConvFrequency")
        tgid = root.find(".//TGID")
        name = None

        if conv_freq is not None:
            # channel = f"{dept_name} - {conv_freq.get('Name')}"
            name = conv_freq.get("Name")
        elif tgid is not None:
            # channel = f"{dept_name} - {tgid.get('Name')}"
            name = tgid.get("Name")
        else:
            name = "Unknown Channel"
            # channel = "Unknown Channel"

        return name, dept_name

    def fetch_api(self) -> dict:
        """Fetch the latest state from the scanner API."""
        # _LOGGER.warning(f"Flask for {self._ip_address}")
        # scanner_val = self.send_command("GSI", "xml")

        # Add a cooldown to prevent state from being overwritten by a stale API response
        # if time.time() - self._last_set_volume_time < 2:
        # _LOGGER.warning(
        #    "Skipping volume update due to recent set_volume_level call"
        # )
        #    return

        try:
            response = requests.get(
                f"http://{self._ip_address}:{self._port}/scanner/status",
                timeout=refresh_time - 0.25,
            )
            response.raise_for_status()
            # data = response.json()
            # self._volume = data.get("volume", 0) / 29.0
            # self._mode = data.get("mode", "unknown")
            # self._mode = "Trunk Scan2"
            # self._media_title = data.get("mode", "unknown")
            # _LOGGER.warning(f"Updated status: mode={self._mode}, volume={self._volume}")
        except requests.exceptions.RequestException:
            _LOGGER.error("Error fetching status from API")
            # self._state = MediaPlayerState.OFF
            # self._volume = 0
            # self._mode = "unknown"

        return {
            "channel": "TODO",
            "dept_name": "TODO",
            "mode": "Trunk Scan",
            "volume": 5,
            "error": None,
        }

    def update_ui(self, display_info) -> None:
        """Update the UI elements."""
        # _LOGGER.warning("Updating UI elements")
        self._volume = 0
        self._mode = display_info[
            "mode"
        ]  # This is key to making it lookg available or not
        self._media_title = display_info["channel"]
        self._media_artist = display_info["dept_name"]

    def set_volume_level(self, volume: float) -> None:
        """Set volume level, a float from 0 to 1."""
        try:
            # Scale volume from 0-1 to 0-29
            level = int(round(volume * 29))
            response = requests.post(
                f"http://{self._ip_address}:{self._port}/scanner/volume",
                json={"volume_level": level},
                timeout=2,
            )
            response.raise_for_status()
            # Immediately update the internal state to prevent the slider from jumping back
            self._volume = int(volume)
            self._last_set_volume_time = time.time()
        except requests.exceptions.RequestException:
            _LOGGER.error("Error setting volume via API")

    def volume_up(self) -> None:
        """Volume up the scanner by one step."""
        # Calculate the next volume level on the scanner's 0-29 integer scale
        current_level = int(round(self._volume * 29))
        new_level = min(29, current_level + 1)
        self.set_volume_level(new_level / 29.0)

    def volume_down(self) -> None:
        """Volume down the scanner by one step."""
        # Calculate the next volume level on the scanner's 0-29 integer scale
        current_level = int(round(self._volume * 29))
        new_level = max(0, current_level - 1)
        self.set_volume_level(new_level / 29.0)

    def get_volume(self) -> int:
        """Get the current volume."""

        # Get current volume
        xml_response = self.send_command("GSI", "xml")
        # _LOGGER.info(f"xml response was: {xml_response}")

        if xml_response:
            try:
                # Parse the XML response from the returned string
                root = parse(xml_response)

                # Get the volume from the Property tag's VOL attribute
                property_info = root.find(".//Property")
                if property_info is not None:
                    vol_str = property_info.get("VOL")
                    if vol_str is not None:
                        # current_volume = int(vol_str)
                        # self._volume = current_volume / 29.0
                        return int(vol_str)

                    _LOGGER.error("VOL attribute not found in Property tag")
                else:
                    _LOGGER.error("No Property tag found in XML response")
            except ET.ParseError:
                _LOGGER.error("Failed to parse XML response from scanner")

        return 0

    def mute_volume(self, mute: bool) -> None:
        """Mute the volume."""

        try:
            current_volume = self.get_volume()
            self._volume = int(current_volume / 29.0)
        except (IndexError, ValueError):
            _LOGGER.error("Error getting value")

        if mute:
            # _LOGGER.warning(f"Muting. Existing volume: {self._volume}")
            self._unmute_volume = self._volume
            # There is no mute command, so we set volume to 0 instead
            self.set_volume_level(0)
        else:
            # _LOGGER.warning(f"UnMuting. Restoring to: {self._unmute_volume}")
            self.set_volume_level(self._unmute_volume)

        self._is_volume_muted = mute

    def media_play(self) -> None:
        """Send play command to scanner."""
        try:
            response = requests.post(
                f"http://{self._ip_address}:{self._port}/scanner/play", timeout=2
            )
            response.raise_for_status()
        except requests.exceptions.RequestException:
            _LOGGER.error("Error sending play command")

    def media_pause(self) -> None:
        """Send pause command to scanner."""
        try:
            response = requests.post(
                f"http://{self._ip_address}:{self._port}/scanner/pause", timeout=2
            )
            response.raise_for_status()
        except requests.exceptions.RequestException:
            _LOGGER.error("Error sending pause command")

    def media_next_track(self) -> None:
        """Send next track command to scanner."""
        try:
            response = requests.post(
                f"http://{self._ip_address}:{self._port}/scanner/next", timeout=2
            )
            response.raise_for_status()
        except requests.exceptions.RequestException:
            _LOGGER.error("Error sending next track command")

    async def async_turn_off(self) -> None:
        """Reboot the device."""
        self.send_command("MSM,1", "xml")

    def set_offline(self) -> None:
        """Set the scanner to offline state."""
        self._state = MediaPlayerState.OFF
        self._volume = 0
        self._mode = "offline"
        self._reachable = False

    def set_online(self) -> None:
        """Set the scanner to online state."""
        self._state = MediaPlayerState.PLAYING
        self._volume = 3
        self._mode = "Trunk Scan"
        self._reachable = True
