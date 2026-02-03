import asyncio
import sys
from utils.wiz_utils import apply_preset, load_presets, get_light_ips

async def main():
    print("--- Diagnosticando Presets ---")
    
    # 1. Check presets loading
    presets = load_presets()
    print(f"Presets cargados: {list(presets.keys())}")
    
    if "dormir" not in presets:
        print("❌ Error: Preset 'dormir' no encontrado")
        return
        
    scene = presets["dormir"]
    print(f"Detalle de 'dormir': {scene}")
    
    # 2. Check IPs resolution
    for step in scene:
        light_name = step.get("light")
        ips = get_light_ips(light_name)
        print(f"Luz '{light_name}' resuelve a IPs: {ips}")
        if not ips:
            print(f"❌ Error: No se encontraron IPs para '{light_name}'")
    
    # 3. Apply preset
    print("\n--- Aplicando Preset 'dormir' ---")
    result = await apply_preset("dormir")
    print(f"Resultado: {result}")

if __name__ == "__main__":
    # Force loading environment if needed
    from dotenv import load_dotenv
    load_dotenv()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
