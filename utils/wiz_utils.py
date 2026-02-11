"""Utilities for controlling WIZ lights."""
import asyncio
from utils.config_loader import get_config

# Lazy load pywizlight to avoid import errors if not installed
_wizlight = None
_PilotBuilder = None

def _load_pywizlight():
    """Lazy load pywizlight module."""
    global _wizlight, _PilotBuilder
    if _wizlight is None:
        try:
            from pywizlight import wizlight, PilotBuilder
            _wizlight = wizlight
            _PilotBuilder = PilotBuilder
        except ImportError:
            return False
    return True

def is_wiz_available() -> bool:
    """Check if pywizlight is available."""
    try:
        from pywizlight import wizlight
        return True
    except ImportError:
        return False

def get_light_ips(name: str) -> list[str]:
    """Get IP addresses for a light by name. Returns list (supports groups)."""
    lights = get_config("WIZ_LIGHTS")
    if not lights:
        return []
    
    value = lights.get(name.lower())
    if value is None:
        return []
    
    # Support both single IP (string) and multiple IPs (list)
    if isinstance(value, list):
        return value
    return [value]

def get_all_lights() -> dict:
    """Get all configured lights."""
    return get_config("WIZ_LIGHTS") or {}

# Color name to RGB mapping (supports both English and Spanish)
COLOR_MAP = {
    # English
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "pink": (255, 105, 180),
    "purple": (128, 0, 128),
    "violet": (238, 130, 238),
    "skyblue": (135, 206, 235),
    "white": None,  # Use color temperature instead
    "warm": None,
    "cool": None,
    # Spanish
    "rojo": (255, 0, 0),
    "verde": (0, 255, 0),
    "azul": (0, 0, 255),
    "amarillo": (255, 255, 0),
    "naranja": (255, 165, 0),
    "rosa": (255, 105, 180),
    "morado": (128, 0, 128),
    "violeta": (238, 130, 238),
    "celeste": (135, 206, 235),
    "blanco": None,
    "calido": None,
    "frio": None,
}

async def turn_on_light(ip: str, brightness: int = 100, color: str = None) -> bool:
    """Turn on a light with optional brightness and color."""
    if not _load_pywizlight():
        return False
    
    try:
        light = _wizlight(ip)
        
        if color and color.lower() in COLOR_MAP:
            rgb = COLOR_MAP[color.lower()]
            if rgb:
                await light.turn_on(_PilotBuilder(rgb=rgb, brightness=brightness))
            elif color.lower() in ("calido", "warm"):
                await light.turn_on(_PilotBuilder(colortemp=2700, brightness=brightness))
            elif color.lower() in ("frio", "cool"):
                await light.turn_on(_PilotBuilder(colortemp=6500, brightness=brightness))
            else:
                await light.turn_on(_PilotBuilder(colortemp=4000, brightness=brightness))
        else:
            await light.turn_on(_PilotBuilder(brightness=brightness))
        
        return True
    except Exception as e:
        print(f"[WIZ] Error turning on {ip}: {e}")
        return False

async def turn_off_light(ip: str) -> bool:
    """Turn off a light."""
    if not _load_pywizlight():
        return False
    
    try:
        light = _wizlight(ip)
        await light.turn_off()
        return True
    except Exception as e:
        print(f"[WIZ] Error turning off {ip}: {e}")
        return False

async def control_light(name: str, action: str, value: str = None) -> str:
    """
    Main function to control a light or group of lights.
    name: light name (supports groups with multiple IPs)
    action: "encender", "apagar", "brillo", "color"
    value: brightness level or color name
    """
    lights = get_all_lights()
    
    if not lights:
        return "⚠️ No lights configured"
    
    # Handle "todas"/"all" (all lights) - flatten all IPs
    if name.lower() in ("todas", "all"):
        all_ips = []
        for v in lights.values():
            if isinstance(v, list):
                all_ips.extend(v)
            else:
                all_ips.append(v)
        ips = all_ips
        display_name = "All lights"
    else:
        # Get IPs for the named light/group
        ips = get_light_ips(name)
        if not ips:
            available = ", ".join(lights.keys())
            return f"⚠️ Light '{name}' not found. Available: {available}"
        display_name = f"Light {name}"
    
    # Apply action to all IPs
    results = []
    for ip in ips:
        if action in ("apagar", "off"):
            success = await turn_off_light(ip)
        elif action in ("encender", "on"):
            success = await turn_on_light(ip)
        elif action in ("brillo", "brightness") and value:
            level = max(0, min(100, int(value)))
            success = await turn_on_light(ip, brightness=level)
        elif action == "color" and value:
            success = await turn_on_light(ip, color=value)
        else:
            success = False
        results.append(success)
    
    # Build response
    if all(results):
        if action in ("apagar", "off"):
            return f"💡 {display_name}: off"
        elif action in ("encender", "on"):
            return f"💡 {display_name}: on"
        elif action in ("brillo", "brightness"):
            return f"💡 {display_name}: brightness {value}%"
        elif action == "color":
            return f"💡 {display_name}: color {value}"
    elif any(results):
        return f"⚠️ {display_name}: some lights failed"
    else:
        return f"❌ Error controlling {display_name}"
