"""Oberflaeche zeichnen und fotografieren (Blender mit Fenster):
    blender --factory-startup? nein: mit BLENDER_USER_RESOURCES, in dem das Add-on installiert ist
    blender --python guitest.py -- <spiel> <ausgabeordner>
"""
import os
import sys
import traceback

import addon_utils
import bpy

args = sys.argv[sys.argv.index("--") + 1:]
SPIEL, AUS = args
os.makedirs(AUS, exist_ok=True)
VER = "%d%d" % bpy.app.version[:2]
log = open(os.path.join(AUS, "gui_%s.txt" % VER), "w", encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


def fenster():
    w = bpy.context.window_manager.windows[0]
    area = max((a for a in w.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    return w, area


def foto(name):
    w, area = fenster()
    with bpy.context.temp_override(window=w, area=area):
        bpy.ops.screen.screenshot(filepath=os.path.join(AUS, "gui_%s_%s.png" % (VER, name)))
    p("  Foto", name)


schritt = [0]


def ablauf():
    try:
        s = schritt[0]
        schritt[0] += 1
        w, area = fenster()
        sp = area.spaces.active
        if s == 0:
            name = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith("kotor_import"))
            addon_utils.enable(name, default_set=True)
            bpy.context.preferences.addons[name].preferences.spielordner = SPIEL
            for o in list(bpy.data.objects):
                bpy.data.objects.remove(o)
            sp.show_region_ui = True
            # Der Reiter laesst sich per Python nicht umschalten: fuer die Fotos
            # kommen die Panels in den offenen Reiter "Tool".
            ui = sys.modules[name + ".ui"]
            for k in (ui.KOTOR_PT_figuren, ui.KOTOR_PT_anims):
                bpy.utils.unregister_class(k)
                k.bl_category = "Tool"
                bpy.utils.register_class(k)
            p("Blender", bpy.app.version_string, "Modul", name)
            return 1.0
        if s == 1:
            foto("1_start")
            with bpy.context.temp_override(window=w, area=area):
                bpy.ops.kotor.spiel_laden()
            wm = bpy.context.window_manager
            wm.kotor_figur_index = next(n for n, it in enumerate(wm.kotor_figuren) if it.name == "Party NPC Bastila")
            return 1.0
        if s == 2:
            foto("2_liste")
            reg = next(r for r in area.regions if r.type == "WINDOW")
            with bpy.context.temp_override(window=w, area=area, region=reg):
                bpy.ops.kotor.importieren()
                bpy.ops.view3d.view_axis(type="FRONT")
                bpy.ops.view3d.view_selected()
            sp.shading.type = "MATERIAL"
            wm = bpy.context.window_manager
            wm.kotor_anim_index = next(n for n, a in enumerate(wm.kotor_anims) if a.name == "walk")
            with bpy.context.temp_override(window=w, area=area):
                bpy.ops.kotor.anim_zeigen()
            bpy.context.scene.frame_set(8)
            return 10.0
        if s == 3:
            foto("3_import")
            bpy.ops.wm.quit_blender()
            return None
    except Exception:
        p(traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(ablauf, first_interval=2.0)
