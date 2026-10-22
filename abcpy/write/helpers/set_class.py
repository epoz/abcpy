"""Sets the color and class of drawn elements (port of ``set-class.js``)."""


def set_class(elemset, add_class, remove_class, color):
    if not elemset:
        return
    for el in elemset:
        if el is None:
            continue
        attr = el.get_attribute("highlight")
        if not attr:
            attr = "fill"
        el.set_attribute(attr, color)
        kls = el.get_attribute("class")
        if not kls:
            kls = ""
        kls = kls.replace(remove_class, "", 1) if remove_class else kls
        kls = kls.replace(add_class, "", 1) if add_class else kls
        if len(add_class) > 0:
            if len(kls) > 0 and kls[-1] != ' ':
                kls += " "
            kls += add_class
        el.set_attribute("class", kls)
