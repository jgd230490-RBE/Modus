# The OSTN15 grid (task 4c, site layouts)

`uk_os_OSTN15_NTv2_OSGBtoETRS.tif` is Ordnance Survey's OSTN15 transformation (OSGB 1936 to ETRS89) as PROJ's
GeoTIFF grid, downloaded 31 Oct 2026 from cdn.proj.org (PROJ-data, `uk_os`).
sha256 `5d6ed64d2119952c4c559fa1fccbc594b6520fc3ec3ef2fc10be13202c4384fa`, 3,035,814 bytes.

Licence (the file's own TIFF tag, and PROJ-data's `uk_os_README.txt`): "Derived from work by Ordnance Survey.
The 2-Clause BSD License https://opensource.org/licenses/bsd-license.php". Source: Ordnance Survey; converted
from OSTN15_NTv2_OSGBtoETRS.gsb (version OSTN15, last updated 2016-10-03).

`site_layout_import.py` puts this folder on pyproj's search path with the network off. Without the file a drawing
on National Grid would be placed by a Helmert fit about 2 m out, so the import refuses until it is here.
