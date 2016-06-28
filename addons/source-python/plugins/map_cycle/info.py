from cvars.public import PublicConVar
from plugins.info import PluginInfo


info = PluginInfo()
info.name = "Map Cycle"
info.basename = 'map_cycle'
info.author = 'Kirill "iPlayer" Mysnik'
info.version = '2.0'
info.variable = 'mc_version'
info.convar = PublicConVar(
    info.variable, info.version, "{} version".format(info.name))

info.url = "https://github.com/KirillMysnik/sp-map-cycle"
