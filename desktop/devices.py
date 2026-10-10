# PortAudio is imported lazily. Importing sounddevice initialises PortAudio,
# which costs ~0.6s and blocks the window if it happens at startup; it may also
# be missing entirely on Linux, which must not take the app down.
_sd = None
_sd_error = ""

# PortAudio exposes every endpoint once per host API, so one physical device
# shows up three or four times - and the MME copies of the names are cut off at
# 31 characters. Prefer the modern API whose names are complete; WDM-KS is left
# out because it re-lists the same hardware under unrelated names ("Speakers
# (VB-Audio Point)" for CABLE Input), which cannot be matched up with the rest.
HOST_API_ORDER = ("Windows WASAPI", "Windows DirectSound", "MME")
SKIPPED_HOST_APIS = ("Windows WDM-KS",)
# Two entries are the same device when their names match, or when the shorter
# is a truncation of the longer - never for short, unrelated names.
TRUNCATION_PREFIX_MIN = 25


def _sounddevice():
    global _sd, _sd_error
    if _sd is None and not _sd_error:
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - depends on the host
            _sd_error = str(exc)
        else:
            _sd = sd
    return _sd


def audio_available():
    return _sounddevice() is not None


def unavailable_reason():
    _sounddevice()
    return _sd_error


def _same_device(one, other):
    if one == other:
        return True
    if not one or not other:
        return False
    shorter, longer = (one, other) if len(one) <= len(other) else (other, one)
    return len(shorter) >= TRUNCATION_PREFIX_MIN and longer.startswith(shorter)


def list_output_devices():
    """Return one (index, name) per output device.

    Each physical device is reported once, under the name from the best host
    API available for it, so the picker is not a list of duplicates where some
    entries are cut off mid-word.
    """
    sd = _sounddevice()
    if sd is None:
        return []

    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception:
        return []

    chosen = []
    for index, device in enumerate(devices):
        try:
            if device["max_output_channels"] <= 0:
                continue
            api = hostapis[device["hostapi"]]["name"]
        except Exception:
            continue
        if api in SKIPPED_HOST_APIS:
            continue

        name = device["name"]
        rank = HOST_API_ORDER.index(api) if api in HOST_API_ORDER else len(HOST_API_ORDER)
        lower = name.lower()

        twin = None
        for entry in chosen:
            if _same_device(entry["lower"], lower):
                twin = entry
                break

        if twin is None:
            chosen.append(
                {"index": index, "name": name, "lower": lower, "rank": rank}
            )
        elif (rank, -len(name)) < (twin["rank"], -len(twin["name"])):
            twin.update(index=index, name=name, lower=lower, rank=rank)

    return [(entry["index"], entry["name"]) for entry in chosen]


def find_output_index(keyword, devices):
    """Return the index of the first output device whose name matches keyword."""
    if not keyword:
        return None
    needle = keyword.lower()
    for index, name in devices:
        if needle in name.lower():
            return index
    return None


def default_output_index(devices=None):
    """Index of the default output device, mapped onto ``devices``.

    PortAudio's default may point at an entry that list_output_devices()
    collapsed into another host API's copy, so fall back to the shown entry
    with the matching name.
    """
    sd = _sounddevice()
    if sd is None:
        return None
    try:
        raw = sd.default.device[1]
    except Exception:
        return None
    if raw is None or raw < 0:
        return None
    if not devices:
        return raw

    indices = [index for index, _ in devices]
    if raw in indices:
        return raw

    try:
        wanted = sd.query_devices(raw)["name"].lower()
    except Exception:
        return indices[0]
    for index, name in devices:
        if _same_device(name.lower(), wanted):
            return index
    return indices[0]
