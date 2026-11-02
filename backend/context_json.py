"""Write-through JSON row views; no collection-wide mutable payload cache."""


def tracked(value, changed):
    # Indexed maps own their mutations; wrapping one would copy its payload.
    from analyzers.observation_store import EncryptedRows
    from backend.context_maps import ContextMap
    if isinstance(value, (ContextMap, EncryptedRows)):
        return value
    if isinstance(value, (Object, Array)) and value.changed is changed:
        return value
    if isinstance(value, dict):
        return Object(value, changed)
    if isinstance(value, list):
        return Array(value, changed)
    return value


class Object(dict):
    def __init__(self, value, changed):
        self.changed = changed
        dict.__init__(self, ((key, tracked(child, changed)) for key, child in value.items()))

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, tracked(value, self.changed))
        self.changed()

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self.changed()

    def update(self, *args, **kwargs):
        for key, value in dict(*args, **kwargs).items():
            dict.__setitem__(self, key, tracked(value, self.changed))
        self.changed()

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def pop(self, *args):
        value = dict.pop(self, *args)
        self.changed()
        return value

    def popitem(self):
        value = dict.popitem(self)
        self.changed()
        return value

    def clear(self):
        dict.clear(self)
        self.changed()

    def __ior__(self, value):
        self.update(value)
        return self


class Array(list):
    def __init__(self, value, changed):
        self.changed = changed
        list.__init__(self, (tracked(child, changed) for child in value))

    def __setitem__(self, key, value):
        value = [tracked(child, self.changed) for child in value] if isinstance(key, slice) else tracked(value, self.changed)
        list.__setitem__(self, key, value)
        self.changed()

    def __delitem__(self, key):
        list.__delitem__(self, key)
        self.changed()

    def append(self, value):
        list.append(self, tracked(value, self.changed))
        self.changed()

    def extend(self, values):
        list.extend(self, (tracked(value, self.changed) for value in values))
        self.changed()

    def insert(self, key, value):
        list.insert(self, key, tracked(value, self.changed))
        self.changed()

    def pop(self, *args):
        value = list.pop(self, *args)
        self.changed()
        return value

    def remove(self, value):
        list.remove(self, value)
        self.changed()

    def clear(self):
        list.clear(self)
        self.changed()

    def reverse(self):
        list.reverse(self)
        self.changed()

    def sort(self, *args, **kwargs):
        list.sort(self, *args, **kwargs)
        self.changed()

    def __iadd__(self, values):
        self.extend(values)
        return self

    def __imul__(self, value):
        list.__imul__(self, value)
        self.changed()
        return self
