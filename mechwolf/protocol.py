import json
import tempfile
import webbrowser
from copy import deepcopy
from datetime import timedelta
from math import isclose
from warnings import warn

import yaml
from IPython.display import HTML, Code
from jinja2 import Environment, PackageLoader, select_autoescape

from . import term, ureg
from .apparatus import Apparatus
from .components import ActiveComponent, TempControl, Valve


class Protocol(object):
    """A set of procedures for an apparatus.

    A protocol is defined as a list of procedures, atomic steps for the individual active components of an apparatus.

    Note:
        The same :class:`Apparatus` object can create multiple distinct :class:`Protocol` objects.

    Attributes:
        apparatus (Apparatus): The apparatus for which the protocol is being defined.
        duration (str, optional): The duration of the protocol.
            If None, every step will require an explicit start and stop time.
            If "auto", the duration will be inferred, if possible, during compilation as the end of last procedure in
            protocol.
            If a string, such as "3 minutes", the duration will be explicitly defined. Defaults to None.
        name (str, optional): The name of the protocol. Defaults to "Protocol_X" where *X* is protocol count.
    """

    _id_counter = 0

    def __init__(self, apparatus, duration=None, name=None):
        assert isinstance(apparatus, Apparatus)
        if apparatus.validate():  # ensure apparatus is valid
            self.apparatus = apparatus
        self.procedures = []
        if name is not None:
            self.name = name
        else:
            self.name = "Protocol_" + str(Protocol._id_counter)
            Protocol._id_counter += 1

        # check duration, if given
        if duration not in [None, "auto"]:
            duration = ureg.parse_expression(duration)
            if duration.dimensionality != ureg.hours.dimensionality:
                raise ValueError(
                    term.red(
                        f"{duration.dimensionality} is an invalid unit of measurement for duration. Must be {ureg.hours.dimensionality}"
                    )
                )
        self.duration = duration
        self.is_executing = False
        self.was_executed = False

    def __repr__(self):
        return f"MechWolf protocol for Apparatus {self.apparatus}"

    def _add_single(
        self, component, start="0 seconds", stop=None, duration=None, **kwargs
    ):
        """Adds a single procedure to the protocol.

        See add() for full documentation.
        """

        # make sure that the component being added to the protocol is part of the apparatus
        if component not in self.apparatus.components:
            raise ValueError(
                term.red(f"{component} is not a component of {self.apparatus.name}.")
            )

        # perform the mapping for valves
        if issubclass(component.__class__, Valve) and kwargs.get("setting") is not None:
            try:
                kwargs["setting"] = component.mapping[kwargs["setting"]]
            except KeyError:
                # allow direct specification of valve settings
                if isinstance(kwargs["setting"], int):
                    pass

        # don't let users give empty procedures
        if not kwargs:
            raise RuntimeError(
                term.red(
                    "No kwargs supplied. This will not manipulate the state of your sythesizer. Ensure your call to add() is valid."
                )
            )

        # make sure the component and keywords are valid
        for kwarg, value in kwargs.items():

            if not hasattr(component, kwarg):
                raise ValueError(
                    term.red(
                        f"Invalid attribute {kwarg} for {component}. Valid attributes are {[x for x in vars(component).keys() if x != 'name']}."
                    )
                )

            if (
                isinstance(component.__dict__[kwarg], ureg.Quantity)
                and ureg.parse_expression(value).dimensionality
                != component.__dict__[kwarg].dimensionality
            ):
                raise ValueError(
                    term.red(
                        f"Bad dimensionality of {kwarg} for {component}. Expected dimensionality of {component.__dict__[kwarg].dimensionality} but got {ureg.parse_expression(value).dimensionality}."
                    )
                )

            elif not isinstance(
                component.__dict__[kwarg], type(value)
            ) and not isinstance(component.__dict__[kwarg], ureg.Quantity):
                raise ValueError(
                    term.red(
                        f"Bad type matching. Expected {kwarg} to be {type(component.__dict__[kwarg])} but got {value}, which is of type {type(value)}"
                    )
                )

        if stop is not None and duration is not None:
            raise RuntimeError(
                term.red("Must provide one of stop and duration, not both.")
            )

        # parse the start time if given
        if isinstance(start, timedelta):
            start = str(start.total_seconds()) + " seconds"
        start = ureg.parse_expression(start)

        # parse duration if given
        if duration is not None:
            if isinstance(duration, timedelta):
                duration = str(duration.total_seconds()) + " seconds"
            stop = start + ureg.parse_expression(duration)

        # determine stop time
        if not any([stop, self.duration, duration]):
            raise RuntimeError(
                term.red(
                    "Must specify protocol duration during instantiation in order to omit stop and duration. "
                    f'To automatically set duration of protocol as end of last procedure in protocol, use duration="auto" when creating {self.name}.'
                )
            )
        elif stop is not None:
            if isinstance(stop, timedelta):
                stop = str(stop.total_seconds()) + " seconds"
            if isinstance(stop, str):
                stop = ureg.parse_expression(stop)

        # a little magic for temperature controllers
        if issubclass(component.__class__, TempControl):
            if kwargs.get("temp") is not None and kwargs.get("active") is None:
                kwargs["active"] = True
            elif not kwargs.get("active") and kwargs.get("temp") is None:
                kwargs["temp"] = "0 degC"
            elif kwargs["active"] and kwargs.get("temp") is None:
                raise RuntimeError(
                    term.red(
                        f"TempControl {component} is activated but temperature setting is not given. Specify 'temp' in your call to add()."
                    )
                )

        # add the procedure to the procedure list
        self.procedures.append(
            dict(start=start, stop=stop, component=component, params=kwargs)
        )

    def add(self, component, start="0 seconds", stop=None, duration=None, **kwargs):
        """Adds a procedure to the protocol.

        Warning:
            If stop and duration are both None, the procedure's stop time will be inferred as the end of the protocol.

        Args:
            component_added (ActiveComponent or Iterable): The component(s) for which the procedure being added. If an
                interable, all components will have the same parameters.
            start (str, optional): The start time of the procedure relative to the start of the protocol, such as
                ``"5 seconds"``. May also be a :class:`datetime.timedelta`. Defaults to ``"0 seconds"``, *i.e.* the
                beginning of the protocol.
            stop (str, optional): The stop time of the procedure relative to the start of the protocol, such as
                ``"30 seconds"``. May also be a :class:`datetime.timedelta`. May not be given if ``duration`` is
                used. Defaults to None.
            duration (str, optional): The duration of the procedure, such as "1 hour". May also be a
                :class:`datetime.timedelta`. May not be used if ``stop`` is used. Defaults to None.
            **kwargs: The state of the component for the procedure.

        Raises:
            TypeError: A component is not of the correct type (*i.e.* a Component object)
            ValueError: An error occurred when attempting to parse the kwargs.
            RuntimeError: Stop time of procedure is unable to be determined or invalid component.
        """

        try:
            iter(component)
        except TypeError:
            component = [component]

        for _component in component:
            self._add_single(
                _component, start=start, stop=stop, duration=duration, **kwargs
            )

    def compile(self, warnings=True, _visualization=False):
        """Compile the protocol into a dict of devices and their procedures.

        Args:
            warnings (bool, optional): Whether to warn the user of automatic inferences and non-fatal issues.
                Default (and *highly* recommended setting) is True.

        Returns:
            dict: A dict with the names of components as the values and lists of their procedures as the value.
            The elements of the list of procedures are dicts with two keys: "time", whose value is a pint Quantity,
            and "params", whose value is a dict of parameters for the procedure.

        Raises:
            RuntimeError: When compilation fails.
        """
        output = {}

        # infer the duration of the protocol
        if self.duration == "auto":
            self.duration = sorted(
                [x["stop"] for x in self.procedures],
                key=lambda z: z.to_base_units().magnitude
                if isinstance(z, ureg.Quantity)
                else 0,
            )
            if all([x is None for x in self.duration]):
                raise RuntimeError(
                    term.red(
                        'Unable to automatically infer duration of protocol. Must define stop for at least one procedure to use duration="auto".'
                    )
                )
            self.duration = self.duration[-1]

        # deal only with compiling active components
        for component in [
            x
            for x in self.apparatus.components
            if issubclass(x.__class__, ActiveComponent)
        ]:
            # make sure all active components are activated, raising warning if not
            if component not in [x["component"] for x in self.procedures]:
                if warnings:
                    warn(
                        term.yellow(
                            f"{component} is an active component but was not used in this procedure. If this is intentional, ignore this warning. To suppress this warning, use warnings=False."
                        )
                    )

            # determine the procedures for each component
            component_procedures = sorted(
                [x for x in self.procedures if x["component"] == component],
                key=lambda x: x["start"],
            )

            # skip compilation of components with no procedures added
            if not len(component_procedures):
                continue

            # check for conflicting continuous procedures
            if (
                len(
                    [
                        x
                        for x in component_procedures
                        if x["start"] is None and x["stop"] is None
                    ]
                )
                > 1
            ):
                raise RuntimeError(
                    term.red(
                        (
                            f"{component} cannot have two procedures for the entire duration of the protocol. "
                            "If each procedure defines a different attribute to be set for the entire duration, combine them into one call to add(). "
                            "Otherwise, reduce ambiguity by defining start and stop times for each procedure."
                        )
                    )
                )

            for i, procedure in enumerate(component_procedures):
                # ensure that the start time is before the stop time if given
                if (
                    procedure["stop"] is not None
                    and procedure["start"] > procedure["stop"]
                ):
                    raise RuntimeError(
                        term.red("Start time must be less than or equal to stop time.")
                    )

                # make sure that the start time isn't outside the duration
                if (
                    self.duration is not None
                    and procedure["start"] is not None
                    and procedure["start"] > self.duration
                ):
                    raise ValueError(
                        term.red(
                            f"Procedure cannot start at {procedure['start']}, which is outside the duration of the experiment ({self.duration})."
                        )
                    )

                # make sure that the end time isn't outside the duration
                if (
                    self.duration is not None
                    and procedure["stop"] is not None
                    and procedure["stop"] > self.duration
                ):
                    raise ValueError(
                        term.red(
                            f"Procedure cannot end at {procedure['stop']}, which is outside the duration of the experiment ({self.duration})."
                        )
                    )

                # automatically infer start and stop times
                try:
                    if component_procedures[i + 1]["start"] == ureg.parse_expression(
                        "0 seconds"
                    ):
                        raise RuntimeError(
                            term.red(
                                f"Ambiguous start time for {procedure['component']}."
                            )
                        )
                    elif (
                        component_procedures[i + 1]["start"] is not None
                        and procedure["stop"] is None
                    ):
                        if warnings:
                            warn(
                                term.yellow(
                                    f"Automatically inferring stop time for {procedure['component']} as beginning of {procedure['component']}'s next procedure. To suppress this warning, use warnings=False."
                                )
                            )
                        procedure["stop"] = component_procedures[i + 1]["start"]
                except IndexError:
                    if procedure["stop"] is None:
                        if warnings:
                            warn(
                                term.yellow(
                                    f"Automatically inferring stop for {procedure['component']} as the end of the protocol. To override, provide stop in your call to add(). To suppress this warning, use warnings=False."
                                )
                            )
                        procedure["stop"] = self.duration

            # give the component instructions at all times
            compiled = []
            for i, procedure in enumerate(component_procedures):
                if _visualization:
                    compiled.append(
                        dict(
                            start=procedure["start"],
                            stop=procedure["stop"],
                            params=procedure["params"],
                        )
                    )
                else:
                    compiled.append(
                        dict(time=procedure["start"], params=procedure["params"])
                    )

                    # if the procedure is over at the same time as the next procedure begins, don't go back to the base state
                    try:
                        if isclose(
                            component_procedures[i + 1]["start"]
                            .to_base_units()
                            .magnitude,
                            procedure["stop"].to_base_units().magnitude,
                        ):
                            continue
                    except IndexError:
                        pass

                    # otherwise, go back to base state
                    compiled.append(
                        dict(time=procedure["stop"], params=component.base_state())
                    )

            output[component] = compiled

            # raise warning if duration is explicitly given but not used?
        return output

    def json(self, warnings=True):
        """Compiles protocol and outputs to JSON.

        Args:
            warnings (bool, optional): See :meth:`Protocol.compile` for full explanation of this argument.

        Returns:
            str: JSON of the compiled protocol. When in Jupyter, this string is wrapped in a :class:`IPython.display.Code` object for nice syntax highlighting.

        Raises:
            Same as :meth:`Protocol.compile`.
        """
        compiled = deepcopy(self.compile(warnings=warnings))
        for item in compiled.items():
            for procedure in item[1]:
                procedure["time"] = procedure["time"].to_timedelta().total_seconds()
        compiled = {k.name: v for (k, v) in compiled.items()}
        compiled_json = json.dumps(compiled, sort_keys=True, indent=4)

        try:
            get_ipython
            return Code(compiled_json, language="json")
        except NameError:
            pass
        return compiled_json

    def dict(self, warnings=True):
        compiled = deepcopy(self.compile(warnings=warnings))
        for item in compiled.items():
            for procedure in item[1]:
                procedure["time"] = procedure["time"].to_timedelta().total_seconds()
        compiled = {k.name: v for (k, v) in compiled.items()}
        return compiled

    def yaml(self, warnings=True):
        """Compiles protocol and outputs to YAML.

        Internally, this is a conversion of the output of :meth:`Protocol.json`
        for the purpose of enhanced human readability.

        Args:
            warnings (bool, optional): See :meth:`Protocol.compile` for full explanation of this argument.

        Returns:
            str: YAML of the compiled protocol. When in Jupyter, this string is wrapped in a :class:`IPython.display.Code` object for nice syntax highlighting.

        Raises:
            Same as :meth:`Protocol.compile`.
        """
        compiled_yaml = yaml.safe_dump(json.loads(str(self.json(warnings=warnings))))

        try:
            get_ipython
            return Code(compiled_yaml, language="yaml")
        except NameError:
            pass
        return compiled_yaml

    def visualize(self, browser=True):
        """Generates a Gantt plot visualization of the protocol.

        Args:
            browser (bool, optional): Whether to open in the browser. Defaults to true.

        Returns:
            str: The html of the visualization. When in Jupyter, this string is wrapped in a :class:`IPython.display.HTML` object for interactive display.

        Raises:
            ImportError: When the visualization package is not installed.
        """

        # render the html
        env = Environment(
            autoescape=select_autoescape(["html", "xml"]),
            loader=PackageLoader("mechwolf", "templates"),
        )
        visualization = env.get_template("viz_div.html").render(
            procedures=self.procedures
        )

        # show it in Jupyter, if possible
        try:
            get_ipython()
            return HTML(visualization)
        except NameError:
            pass

        template = env.get_template("visualizer.html")
        visualization = template.render(title=self.name, visualization=visualization)

        if browser:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
                tmp.write(visualization.encode("utf-8"))
                webbrowser.open("file://" + tmp.name)

        return visualization

    def execute(self):
        """Executes the procedure.

        Note:
            Must only contain :class:`~mechwolf.components.component.ActiveComponent` s that have an
            update method, i.e. real components.

        Raises:
            RuntimeError: When attempting to execute a protocol on invalid components.
        """

        # Ensure that execution isn't happening on invalid components
        # if not all([validate_component(x["component"]) for x in self.procedures]):
        #     raise RuntimeError(term.red(f"Attempting to execute protocol on invalid component {x['component']}. Aborted.")
        #
        # if confirmation:
        #     confirm("Are you sure you want to execute this procedure?", abort=True, default=True)
        #
        # # subit the protocol to the hub
        # try:
        #     response = requests.post(f"{address}/submit_protocol", data=dict(protocol=self.json()), verify=False).text
        #     if response == "protocol rejected: different protocol being executed":
        #         raise RuntimeError(term.red("Protocol rejected because hub is currently executing a different protocol.")
        #     elif response != "protocol rejected: invalid signature":
        #         print(f"Protocol id: {response}")
        # except BaseException:
        #     pass
        # warn("This functions has been temporarily deprecated", DeprecationWarning)
        try:
            get_ipython
            from .execute import jupyter_execute

            return jupyter_execute(self)
        except NameError:
            from .execute import execute

            return execute(self)