# Creating New Components

## General Approach

You may find yourself in the position of needing a component that is currently not included in MechWolf.
In that case, you'll have to create your own component.
Here's how:

1.  **Decide what kind of component it is.**  
    If you're trying to make a new kind of pump, for example, you'll want to be inheriting from `Pump`.
    For components being controlled (_i.e._ not aliases of `Component`), you'll have to create a subclass of `ActiveComponent`.

2.  **Create a new class.**  
    If you're struggling, see [the official Python docs](https://docs.python.org/3/tutorial/classes.html), a handy [tutorial on classes](https://www.tutorialspoint.com/python3/python_classes_objects.htm), or look at MechWolf's source code.
    Make sure to add `name` as an optional argument to `__init__` and the line `super().__init__(name=name)`, which tells Python to pass the name argument up to the `ActiveComponent` class.

3.  **Give the component its controllable attributes.**  
    This means that anything that you will be using as keywords during your calls to `Protocol.add()` must be attributes.
    Furthermore, if they are quantities such as "10 mL/min", these attributes should be parsed `Quantity` objects.
    To get a `Quantity` object, import MechWolf's internal Unit registry (_i.e._ using `from mechwolf import _ureg`) and call `_ureg.parse_expression()` with the string of the component's attributes.

4.  **Give it a base state attribute.**  
    MechWolf requires that any component being modified as part of a protocol have a base state attribute to which it will return to after the protocol.
    For things that turn on, this base state is usually "off".
    The base state method must be called `_base_state` and be a dict with attributes as keys and settings for those attributes as values.
    For a Varian pump, it could look like this:

    ```python
    >>> VarianPump()._base_state
    {"rate": "0 mL/min"}
    ```

    The values in the base state dictionary need to be parsable into valid values, the same as if they were passed as keyword arguments to `Protocol.add()`.
    In fact, under the hood, that is exactly what is happening.
    At the end of your protocol, `Protocol.compile()` adds a procedure for each `ActiveComponent` in the protocol to return to its base state.
    In addition, when the component is not explicitly being used, the component will default to its base state.

5.  **Give it a method to update the hardware's state.**  
    The job of the update method is to make the object's real-world state match its virtual representation.
    The update method must be asynchronous and be called `_update()`.
    This is where the hardware interfacing happens.

    Note, however, that because MechWolf objects have two distinct uses (being manipulated before runtime and actually used during runtime to control the hardware), components must be able to be instantiated without respect to their real-world configuration.
    For example, this means that, to enforce a level of abstraction, you shouldn't need to know what serial port your client is talking to your component in order to manipulate it when creating your script.
    The object that is being run on your client _would_ need to know that though, so the object has to be able to support both uses.

    Note: this step doesn't apply to `Sensor`s, which already have a built-in update method.

6.  **For sensors, give it a method to read the data.**

    This is where the actual data collection goes.
    The method must be called `_read()`.
    It should asynchronously return the data read in from the sensor, which may be in any JSON-serializable format.
    MechWolf will automatically timestamp and log it, so don't worry about that.

7.  \*\*Test thoroughly with `validate_component`.  
    For your convenience, the `validate_component`
    function will take an instance of your class (not the class
    itself) and verify that it meets the requirements to be used in
    a protocol.

8.  **Contribute to GitHub** _(optional)_  
    Odds are you're not the only person in the world who could use
    the component you're making. In the spirit of collaboration, we
    welcome any and all components submitted to us that are
    compatible with our API and encourage you to submit your
    component in a pull request.

## Example: Making the Philosopher's Stone

Let's say that you discovered the [philosopher's
stone](https://en.wikipedia.org/wiki/Philosopher%27s_stone), which is
capable of turning anything into gold. But that's not good enough. You
want an automated philosopher's stone with MechWolf\!

To make it work with MechWolf, we'll follow the process of creating a
new component by making a blank class that inherits from
`components.component.ActiveComponent`:

    from mechwolf import ActiveComponent

    class PhilosophersStone(ActiveComponent):
        def __init__(self, name=None):
            super().__init__(name=name)

For attributes, let's imagine that the philosopher's stone can convert a
variable mass of the solution flowing through it into gold:

    from mechwolf import ActiveComponent, ureg

    class PhilosophersStone(ActiveComponent):
        def __init__(self, name=None):
            super().__init__(name=name)
            self.rate = ureg.parse_expression("0 g/min")

Now we'll need a base state:

    from mechwolf import ActiveComponent, ureg

    class PhilosophersStone(ActiveComponent):
        def __init__(self, name=None):
            super().__init__(name=name)
            self.rate = ureg.parse_expression("0 g/min")

        def base_state(self):
            return dict(rate="0 g/min")

And finally, a way to update it. Here, we'll have to rely on our
imagination:

    from mechwolf import ActiveComponent, ureg

    class PhilosophersStone(ActiveComponent):
        def __init__(self, name=None, serial_port=None):
            super().__init__(name=name)
            self.rate = ureg.parse_expression("0 g/min")
            self.serial_port = serial_port

        def base_state(self):
            return dict(rate="0 g/min")

        async def update(self):
            # magic goes here
            yield

Saving it as `philosophersstone.py`, we can then use
`validate_component` to test if instances of the class are
valid:

    >>> import mechwolf as mw
    >>> from philosophersstone import PhilosophersStone
    >>> stone = PhilosophersStone(name="stone")
    >>> mw.validate_component(stone)
    True

`validate_component` returned `True`, meaning that the
philosopher's stone class is facially valid.

## Example: The Vici Valve

The last example, though illustrative, isn't actually a working
component, since (unfortunately) philosophers' stones don't exist.
Luckily, we have the next best thing: a Vici valve. To show how to
create working components, we'll walk through MechWolf's implementation
of `components.vici.ViciValve`.

First, we need to include the import statements at the top. We
communicate with Vici valves via serial on the client, but don't
actually _need_ the serial package in order to instantiate a
`components.vici.ViciValve` object. That's because you need to
be able to instantiate `components.vici.ViciValve` objects on
devices without the client extras installed (which includes the serial
package), such as when designing apparatuses on your personal computer.
For that reason, the import statement (in this case `import aioserial`) is 
placed in the class `__enter__` magic method (also called dunder method, from
the double underscore).

<div class="literalinclude" data-lines="38-40">

../../../mechwolf/components/contrib/vici.py

</div>

The `__enter__` magic method is then executed when entering the component's 
context, _i.e._ in the experiment main function.

<div class="literalinclude" data-lines="43-47">

../../../mechwolf/core/execute.py

</div>

Because Vici valves are subclasses of
`components.stdlib.Valve`, we also need to import
`components.stdlib.Valve`.
Since `vici.py` is in the `components/contrib` folder, while
`Valve` is in `components/stdlib`, we can use a local import:

<div class="literalinclude" data-lines="3">

../../../mechwolf/components/contrib/vici.py

</div>

If we were creating the object in a different directory, we would import
`components.stdlib.Valve` the usual way:

    from mechwolf import Valve

Now that we have got the modules that we will need, let's create the class:

<div class="literalinclude" data-lines="6-8">

../../../mechwolf/components/contrib/vici.py

</div>

And we'll create an `__init__()` method:

<div class="literalinclude" data-pyobject="ViciValve.__init__">

../../../mechwolf/components/contrib/vici.py

</div>

Note that the arguments include the ones required by
`components.valve.Valve` (`name` and `mapping`) and
`serial_port`, which is needed to connect to the physical component on
the client.

We can skip adding a base state because
`components.stdlib.Valve` already has one, meaning that
`components.vici.ViciValve` will inherit it automatically.

<div class="literalinclude" data-lines="34">

../../../mechwolf/components/stdlib/valve.py

</div>


Now for the important parts: we need to make the object be able to make
its real-world state match the object's state. We do that with the
`update` method. It needs to be an `async` function that yields data to
be reported back to the hub. This is the driver, the heart of the
component that allows for execution:

<div class="literalinclude" data-pyobject="ViciValve.update">

../../../mechwolf/components/contrib/vici.py

</div>

The exact implementation will vary from component to component, but the
basic idea is that it sends the message in a format that the component
can understand.

One thing to know about serial connections is that they need to be
opened and closed. However, you don't want to open and close the
connection after every procedure, especially if you will be doing a lot of
procedures in a short interval of time. Instead, you want to open the connection
once at the beginning and close it at the end when you are done with the
component. MechWolf can handle that automatically if you give it some
additional information, namely functions called `__enter__` and
`__exit__`.

In Vici valves, `__enter__` creates a serial connection once when you
start the client and then returns `self`:

<div class="literalinclude" data-pyobject="ViciValve.__enter__">

../../../mechwolf/components/contrib/vici.py

</div>

Similarly, `__exit__` closes the connection:

<div class="literalinclude" data-pyobject="ViciValve.__exit__">

../../../mechwolf/components/contrib/vici.py

</div>

[PEP 343](https://www.python.org/dev/peps/pep-0343/) and this [StackOverflow
answer](https://stackoverflow.com/questions/1984325/explaining-pythons-enter-and-exit)
have more about information about how to use `__enter__` and `__exit__`
methods.

That's it\! We now have a functioning Vici valve. Let's test it with
`validate_component`:

    >>> import mechwolf as mw
    >>> mw.validate_component(mw.ViciValve(name="test", mapping={}))
    True

Sure enough, it works. This isn't just an example however, it's exactly
how the Vici valve in the `components.vici` module works\!

If you're stuck trying to make a new component, don't hesitate to reach
out for `help <support>`.

## A Note on Naming

Be sure to follow MechWolf's naming convention, especially if you plan
on contributing to the GitHub. Classes are named in CamelCase format in
keeping with [PEP 08's class name
specification](https://www.python.org/dev/peps/pep-0008/#class-names).
