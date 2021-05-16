import re

class units:
    f_to_c = lambda n: int(round((n - 32)*5/9,0))
    mi_to_km = lambda n: int(round(n * 1.609, 0))
    
    def imperial_string_to_metric(line, *, both=False):
        f_to_c = lambda n: int(round((n - 32)*5/9,0))
        mi_to_km = lambda n: int(round(n * 1.609, 0))
        F_C = re.compile("(-?\d+)°F")
        MI_KM = re.compile("(\d+\.?\d+) mph", flags=re.IGNORECASE)
        def f_c(m):
            c = f_to_c(int(m.group(1)))
            return f"{c}°C" if not both else f"{c}°C / {m.group(0)}"

        def mi_km(m):
            km = mi_to_km(int(float(m.group(1))))
            return f"{km} km/h" if not both else f"{km} km/h / {m.group(0)}"

        line = F_C.sub(f_c, line)
        line = MI_KM.sub(mi_km, line)

        return line


    def bearing_to_compass(bearing):
        dirs = {}        
        dirs['N'] = (348.75, 11.25)
        dirs['NNE'] = (11.25, 33.75)
        dirs['NE'] = (33.75, 56.25)
        dirs['ENE'] = (56.25, 78.75)
        dirs['E'] = (78.75, 101.25)
        dirs['ESE'] = (101.25, 123.75)
        dirs['SE'] = (123.75, 146.25)
        dirs['SSE'] = (146.25, 168.75)
        dirs['S'] = (168.75, 191.25)
        dirs['SSW'] = (191.25, 213.75)
        dirs['SW'] = (213.75, 236.25)
        dirs['WSW'] = (236.25, 258.75)
        dirs['W'] = (258.75, 281.25)
        dirs['WNW'] = (281.25, 303.75)
        dirs['NW'] = (303.75, 326.25)
        dirs['NNW'] = (326.25, 348.75)

        for direction in dirs:
            min, max = dirs[direction]
            if bearing >= min and bearing <= max:
                return direction
            elif bearing >= dirs['N'][0] or bearing <= dirs['N'][1]:
                return "N"

    def bearing_to_arrow(bearing):
        directions = {
            "↓": (337.5, 22.5),
            "↘︎": (292.5, 337.5),
            "→": (247.5, 292.5),
            "↗︎": (202.5, 247.5),
            "↑": (157.5, 202.5),
            "↖︎": (112.5 ,157.5),
            "←": (67.5, 112.5),
            "↙︎": (22.5, 67.5)
        }
        for direction in directions:
            min, max = directions[direction]
            if bearing >= min and bearing <= max:
                return direction
            elif bearing >= directions['↓'][0] or bearing <= directions['↓'][1]:
                return '↓'

