import types


def create_registry(desc="", *, frozen=False):
    """Create a new registry dictionary.

    Args:
        desc: registry docstring.
        frozen: if True, re-registering an existing name raises (append-only).
            Reproducibility-friendly for scientific / plugin registries where a
            silent overwrite is a bug.
    """
    return regdict({}, __doc__=desc, __frozen__=frozen)


class regdict(dict):
    """A dict registry that also carries per-entry metadata and an optional
    append-only ("frozen") guard.

    Metadata passed to :func:`register` (the ``description`` and any extra keyword
    arguments) is stored in the :attr:`meta` sidecar keyed by name, so it is
    queryable uniformly via :meth:`where` / :meth:`select` and works even when the
    registered payload is immutable (e.g. a ``@dataclass(frozen=True)``), where
    setting attributes on the payload would fail.
    """

    def __init__(self, *args, __name__=None, __doc__=None, __frozen__=False, **kwargs):
        super().__init__(*args, **kwargs)
        if __doc__:
            self.__doc__ = __doc__
        if __name__:
            self.__name__ = __name__
        self.frozen = __frozen__
        self.meta = {}

    def where(self, **predicates):
        """Names whose metadata matches every ``key=value`` predicate.

        Example: ``reg.where(sign_safe=True, locality="nonlocal")``.
        """
        return [n for n, m in self.meta.items()
                if all(m.get(k) == v for k, v in predicates.items())]

    def select(self, **predicates):
        """The registered payloads whose metadata matches (see :meth:`where`)."""
        return [self[n] for n in self.where(**predicates)]


def register(name: str, registry, description: str = "", *, overwrite=None, **kwargs):
    """Decorator to register a function (or any payload) in a given registry.

    Extra keyword arguments are stored as metadata, queryable via
    :meth:`regdict.where`. If the registry was created with ``frozen=True`` (or
    ``overwrite=False`` is passed), re-registering an existing name raises
    ``ValueError`` instead of silently replacing it.
    """
    frozen = getattr(registry, "frozen", False)
    deny_overwrite = (overwrite is False) or (overwrite is None and frozen)

    def decorator(func):
        if deny_overwrite and name in registry:
            raise ValueError(
                f"{name!r} is already registered and this registry is append-only")
        meta = {"description": description or "No description provided", **kwargs}
        registry[name] = func
        # Store metadata in the registry sidecar (works for immutable payloads too).
        if hasattr(registry, "meta"):
            registry.meta[name] = meta
        # Back-compat: also expose the metadata as attributes when the payload
        # allows it (a plain function does; a frozen dataclass / builtin does not).
        for key, value in {"_correction_name": name,
                           "_description": meta["description"], **kwargs}.items():
            try:
                setattr(func, key, value)
            except (AttributeError, TypeError):
                pass  # immutable payload -> metadata lives in registry.meta
        return func
    return decorator


class Register:
    """
    Base class for bricks that require registration.
    """

    def __init__(self):
        # Each instance gets its own registry
        self.registry = create_registry()

    def register(cls, name: str, description: str = "", **kwargs):
        """Class method that wraps the register decorator for the class's registry."""
        def decorator(func):
            return register(name, cls.registry, description, **kwargs)(func)
        return decorator

    @property
    def available(self):
        return self.registry

    def where(self, **predicates):
        """Names in this instance's registry matching the metadata predicates."""
        return self.registry.where(**predicates)

    def select(self, **predicates):
        """Registered payloads in this instance's registry matching the predicates."""
        return self.registry.select(**predicates)

    # @classmethod
    def get(self, name):
        """Retrieve a registered method by name.
        Args:
            name (str): The name of the method.
        Raises:
            KeyError: If the method is not registered.
        """
        meth = self.available.get(
            name, None)

        if meth is None:
            raise KeyError(
                f"Method '{name}' is not registered.",
                "Check metadata or make sure the method is registered (if custom method).")
        return meth

    # @classmethod
    def add_method(self, name, how=None):
        """Decorator that binds ``func`` to this instance as attribute ``name``.

        The decorated function is returned unchanged, so the name it was defined
        under keeps referring to the function itself (rather than, as a side
        effect, to this ``Register`` instance).
        """
        def decorator(func):
            # Dynamically attach the function to this instance.
            if how == 'classmethod':
                method = classmethod(func)
            elif how == 'static':
                method = func
            else:
                method = types.MethodType(func, self)
            setattr(self, name, method)
            return func
        return decorator

    def apply(self, data, **kwargs):
        """
        Apply the correction routine to the provided data.
        Must be overridden by subclasses.
        """
        raise NotImplementedError(
            "Each correction module must implement an apply() method.")
