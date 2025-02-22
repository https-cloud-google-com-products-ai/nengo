import numpy as np
import pytest

import nengo
import nengo.utils.numpy as npext
from nengo.dists import Choice, Gaussian, UniformHypersphere
from nengo.exceptions import BuildError, NengoWarning
from nengo.processes import WhiteNoise, FilteredNoise
from nengo.utils.testing import allclose


def test_missing_attribute():
    with nengo.Network():
        a = nengo.Ensemble(10, 1)

        with pytest.warns(SyntaxWarning):
            a.new_attribute = 9


@pytest.mark.parametrize("dimensions", [1, 200])
def test_encoders(RefSimulator, dimensions, seed, n_neurons=10, encoders=None):
    dtype = nengo.rc.float_dtype
    if encoders is None:
        encoders = np.random.normal(size=(n_neurons, dimensions))
        encoders = npext.array(encoders, min_dims=2, dtype=dtype)
        encoders /= npext.norm(encoders, axis=1, keepdims=True)

    model = nengo.Network(label="_test_encoders", seed=seed)
    with model:
        ens = nengo.Ensemble(
            n_neurons=n_neurons, dimensions=dimensions, encoders=encoders, label="A"
        )

    with RefSimulator(model) as sim:
        assert np.allclose(encoders, sim.data[ens].encoders)


def test_encoders_wrong_shape(RefSimulator, seed):
    dimensions = 3
    encoders = np.random.normal(size=dimensions)
    with pytest.raises(ValueError):
        test_encoders(RefSimulator, dimensions, seed=seed, encoders=encoders)


def test_encoders_negative_neurons(RefSimulator, seed):
    with pytest.raises(ValueError):
        test_encoders(RefSimulator, 1, seed=seed, n_neurons=-1)


def test_encoders_no_dimensions(RefSimulator, seed):
    with pytest.raises(ValueError):
        test_encoders(RefSimulator, 0, seed=seed)


def test_constant_scalar(Simulator, nl, plt, seed):
    """A Network that represents a constant value."""
    N = 30
    val = 0.5

    m = nengo.Network(seed=seed)
    with m:
        m.config[nengo.Ensemble].neuron_type = nl()
        input = nengo.Node(output=val, label="input")
        A = nengo.Ensemble(N, 1)
        nengo.Connection(input, A)
        in_p = nengo.Probe(input, "output")
        A_p = nengo.Probe(A, "decoded_output", synapse=0.05)

    with Simulator(m) as sim:
        sim.run(0.3)

    t = sim.trange()
    plt.plot(t, sim.data[in_p], label="Input")
    plt.plot(t, sim.data[A_p], label="Neuron approximation, pstc=0.05")
    plt.ylim(top=1.05 * val)
    plt.xlim(right=t[-1])
    plt.legend(loc=0)

    assert np.allclose(sim.data[in_p], val, atol=0.1, rtol=0.01)
    assert np.allclose(sim.data[A_p][-10:], val, atol=0.1, rtol=0.01)


def test_constant_vector(Simulator, nl, plt, seed):
    """A network that represents a constant 3D vector."""
    N = 30
    vals = [0.6, 0.1, -0.5]

    m = nengo.Network(seed=seed)
    with m:
        m.config[nengo.Ensemble].neuron_type = nl()
        input = nengo.Node(output=vals)
        A = nengo.Ensemble(N * len(vals), len(vals))
        nengo.Connection(input, A)
        in_p = nengo.Probe(input, "output")
        A_p = nengo.Probe(A, "decoded_output", synapse=0.05)

    with Simulator(m) as sim:
        sim.run(0.3)

    t = sim.trange()
    plt.plot(t, sim.data[in_p], label="Input")
    plt.plot(t, sim.data[A_p], label="Neuron approximation, pstc=0.05")
    plt.legend(loc="best", fontsize="small")
    plt.xlim(right=t[-1])

    assert np.allclose(sim.data[in_p][-10:], vals, atol=0.1, rtol=0.01)
    assert np.allclose(sim.data[A_p][-10:], vals, atol=0.1, rtol=0.01)


def test_scalar(Simulator, nl, plt, seed):
    """A network that represents sin(t)."""
    N = 40
    f = lambda t: np.sin(2 * np.pi * t)

    m = nengo.Network(label="test_scalar", seed=seed)
    with m:
        m.config[nengo.Ensemble].neuron_type = nl()
        input = nengo.Node(output=f)
        A = nengo.Ensemble(N, 1, label="A")
        nengo.Connection(input, A)
        in_p = nengo.Probe(input, "output")
        A_p = nengo.Probe(A, "decoded_output", synapse=0.02)

    with Simulator(m) as sim:
        sim.run(1.0)
    t = sim.trange()
    target = f(t)

    assert allclose(t, target, sim.data[in_p], rtol=1e-3, atol=1e-5)
    assert allclose(t, target, sim.data[A_p], atol=0.1, delay=0.03, plt=plt)


def test_vector(Simulator, nl, plt, seed):
    """A network that represents sin(t), cos(t), cos(t)**2."""
    N = 100
    f = lambda t: [np.sin(6.3 * t), np.cos(6.3 * t), np.cos(6.3 * t) ** 2]

    m = nengo.Network(label="test_vector", seed=seed)
    with m:
        m.config[nengo.Ensemble].neuron_type = nl()
        input = nengo.Node(output=f)
        A = nengo.Ensemble(N * 3, 3, radius=1.5)
        nengo.Connection(input, A)
        in_p = nengo.Probe(input)
        A_p = nengo.Probe(A, synapse=0.03)

    with Simulator(m) as sim:
        sim.run(1.0)
    t = sim.trange()
    target = np.vstack(f(t)).T

    assert allclose(t, target, sim.data[in_p], rtol=1e-3, atol=1e-5)
    assert allclose(t, target, sim.data[A_p], plt=plt, atol=0.1, delay=0.03, buf=0.1)


def test_product(Simulator, nl, plt, seed):
    N = 80
    dt2 = 0.002
    f = lambda t: np.sin(2 * np.pi * t)

    m = nengo.Network(seed=seed)
    with m:
        m.config[nengo.Ensemble].neuron_type = nl()
        sin = nengo.Node(output=f)
        cons = nengo.Node(output=-0.5)
        factors = nengo.Ensemble(
            2 * N,
            dimensions=2,
            radius=1.5,
            encoders=Choice([[1, 1], [-1, 1], [1, -1], [-1, -1]]),
        )
        product = nengo.Ensemble(N, dimensions=1)
        nengo.Connection(sin, factors[0])
        nengo.Connection(cons, factors[1])
        nengo.Connection(factors, product, function=lambda x: x[0] * x[1], synapse=0.01)

        factors_p = nengo.Probe(factors, sample_every=dt2, synapse=0.01)
        product_p = nengo.Probe(product, sample_every=dt2, synapse=0.01)

    with Simulator(m) as sim:
        sim.run(1)
    t = sim.trange(sample_every=dt2)

    plt.subplot(211)
    plt.plot(t, sim.data[factors_p])
    plt.legend(["factor 1", "factor 2"], loc="best")
    plt.subplot(212)
    plt.plot(t, -0.5 * f(t), "k--")
    plt.plot(t, sim.data[product_p])
    plt.legend(["exact product", "neural product"], loc="best")

    assert npext.rmse(sim.data[factors_p][:, 0], f(t)) < 0.1
    assert npext.rmse(sim.data[factors_p][20:, 1], -0.5) < 0.1
    assert npext.rmse(sim.data[product_p][:, 0], -0.5 * f(t)) < 0.1


@pytest.mark.parametrize("dims, points", [(1, 528), (2, 823), (3, 937)])
def test_eval_points_number(Simulator, dims, points, seed):
    model = nengo.Network(seed=seed)
    with model:
        A = nengo.Ensemble(5, dims, n_eval_points=points)

    with Simulator(model) as sim:
        assert sim.data[A].eval_points.shape == (points, dims)


def test_eval_points_number_warning(Simulator, seed):
    model = nengo.Network(seed=seed)
    with model:
        A = nengo.Ensemble(5, 1, n_eval_points=10, eval_points=[[0.1], [0.2]])

    with pytest.warns(UserWarning):
        # n_eval_points doesn't match actual passed eval_points, which warns
        with Simulator(model) as sim:
            pass

    assert np.allclose(sim.data[A].eval_points, [[0.1], [0.2]])


def test_gain_bias_warning(Simulator, seed):
    model = nengo.Network(seed=seed)
    with model:
        nengo.Ensemble(1, 1, gain=[1], bias=[1], intercepts=[0.5])
        nengo.Ensemble(1, 1, gain=[1], bias=[1], max_rates=[200])

    with pytest.warns(NengoWarning):
        # gain, bias override specified intercepts and max_rates, which warns
        with Simulator(model):
            pass


@pytest.mark.parametrize(
    "neurons, dims", [(10, 1), (392, 1), (2108, 1), (100, 2), (1290, 4), (20, 9)]
)
def test_eval_points_heuristic(Simulator, neurons, dims, seed):
    def heuristic(neurons, dims):
        return max(np.clip(500 * dims, 750, 2500), 2 * neurons)

    model = nengo.Network(seed=seed)
    with model:
        A = nengo.Ensemble(neurons, dims)

    with Simulator(model) as sim:
        points = sim.data[A].eval_points
        assert points.shape == (heuristic(neurons, dims), dims)


@pytest.mark.parametrize("sample", [False, True])
@pytest.mark.parametrize("radius", [0.5, 1, 1.5])
def test_eval_points_scaling(Simulator, sample, radius, seed, rng):
    eval_points = UniformHypersphere()
    if sample:
        eval_points = eval_points.sample(500, 3, rng=rng)

    model = nengo.Network(seed=seed)
    with model:
        a = nengo.Ensemble(1, 3, eval_points=eval_points, radius=radius)

    with Simulator(model) as sim:
        dists = npext.norm(sim.data[a].eval_points, axis=1)
        assert np.all(dists <= radius)
        assert np.any(dists >= 0.9 * radius)


def test_len():
    """Make sure we can do len(ens) or len(ens.neurons)."""
    with nengo.Network():
        ens1 = nengo.Ensemble(10, dimensions=1)
        ens5 = nengo.Ensemble(100, dimensions=5)
    # Ensemble.__len__
    assert len(ens1) == 1
    assert len(ens5) == 5
    assert len(ens1[0]) == 1
    assert len(ens1[-1]) == 1
    assert len(ens5[:3]) == 3
    assert len(ens5[:100]) == 5

    # Neurons.__len__
    assert len(ens1.neurons) == 10
    assert len(ens5.neurons) == 100
    assert len(ens1.neurons[0]) == 1
    assert len(ens5.neurons[90:]) == 10
    assert len(ens5.neurons[90:150]) == 10


def test_invalid_indices():
    with nengo.Network():
        ens = nengo.Ensemble(10, dimensions=2)

    with pytest.raises(IndexError):
        assert ens[5]
    with pytest.raises(IndexError):
        assert ens[-5]
    with pytest.raises(IndexError):
        assert ens.neurons[20]


def test_invalid_rates(Simulator):
    with nengo.Network() as model:
        nengo.Ensemble(1, 1, max_rates=[200], neuron_type=nengo.LIF(tau_ref=0.01))

    with pytest.raises(ValueError):
        with Simulator(model):
            pass


def test_gain_bias(Simulator):

    N = 17
    D = 2

    gain = np.random.uniform(low=0.2, high=5, size=N)
    bias = np.random.uniform(low=1.2, high=2, size=N)

    model = nengo.Network()
    with model:
        a = nengo.Ensemble(N, D)
        a.gain = gain
        a.bias = bias

    with Simulator(model) as sim:
        assert np.array_equal(gain, sim.data[a].gain)
        assert np.array_equal(bias, sim.data[a].bias)


def test_noise_gen(Simulator, nl_nodirect, seed, plt):
    """Ensure that setting Ensemble.noise generates noise."""
    with nengo.Network(seed=seed) as model:
        intercepts = -0.5
        neg_noise, pos_noise = -4, 5
        model.config[nengo.Ensemble].neuron_type = nl_nodirect()
        model.config[nengo.Ensemble].encoders = Choice([[1]])
        model.config[nengo.Ensemble].intercepts = Choice([intercepts])
        pos = nengo.Ensemble(1, 1, noise=WhiteNoise(Gaussian(pos_noise, 0.01)))
        normal = nengo.Ensemble(1, 1)
        neg = nengo.Ensemble(1, 1, noise=WhiteNoise(Gaussian(neg_noise, 0.01)))
        pos_p = nengo.Probe(pos.neurons, synapse=0.1)
        normal_p = nengo.Probe(normal.neurons, synapse=0.1)
        neg_p = nengo.Probe(neg.neurons, synapse=0.1)
    with Simulator(model) as sim:
        sim.run(0.06)

    t = sim.trange()
    plt.title("intercepts=%d" % intercepts)
    plt.plot(t, sim.data[pos_p], c="b", label="noise=%d" % pos_noise)
    plt.plot(t, sim.data[normal_p], c="k", label="no noise")
    plt.plot(t, sim.data[neg_p], c="r", label="noise=%d" % neg_noise)
    plt.legend(loc="best")

    assert np.all(sim.data[pos_p] >= sim.data[normal_p])
    assert np.all(sim.data[normal_p] >= sim.data[neg_p])
    assert not np.allclose(sim.data[normal_p], sim.data[pos_p])
    assert not np.allclose(sim.data[normal_p], sim.data[neg_p])


def test_noise_copies_ok(Simulator, nl_nodirect, seed, plt):
    """Make sure the same noise process works in multiple ensembles.

    We test this both with the default system and without.
    """

    process = FilteredNoise(synapse=nengo.Alpha(1.0), dist=Choice([0.5]))
    with nengo.Network(seed=seed) as model:
        inp, gain, bias = 1, 5, 2
        model.config[nengo.Ensemble].neuron_type = nl_nodirect()
        model.config[nengo.Ensemble].encoders = Choice([[1]])
        model.config[nengo.Ensemble].gain = Choice([gain])
        model.config[nengo.Ensemble].bias = Choice([bias])
        model.config[nengo.Ensemble].noise = process
        const = nengo.Node(output=inp)
        a = nengo.Ensemble(1, 1, noise=process)
        b = nengo.Ensemble(1, 1, noise=process)
        c = nengo.Ensemble(1, 1)  # defaults to noise=process
        nengo.Connection(const, a)
        nengo.Connection(const, b)
        nengo.Connection(const, c)
        ap = nengo.Probe(a.neurons, synapse=0.01)
        bp = nengo.Probe(b.neurons, synapse=0.01)
        cp = nengo.Probe(c.neurons, synapse=0.01)
    with Simulator(model) as sim:
        sim.run(0.06)
    t = sim.trange()

    plt.subplot(2, 1, 1)
    plt.plot(t, sim.data[ap], lw=3)
    plt.plot(t, sim.data[bp], lw=2)
    plt.plot(t, sim.data[cp])
    plt.subplot(2, 1, 2)
    plt.plot(*nengo.utils.ensemble.tuning_curves(a, sim), lw=3)
    plt.plot(*nengo.utils.ensemble.tuning_curves(b, sim), lw=2)
    plt.plot(*nengo.utils.ensemble.tuning_curves(c, sim))

    assert np.allclose(sim.data[ap], sim.data[bp])
    assert np.allclose(sim.data[bp], sim.data[cp])


def test_no_norm_encoders(Simulator):
    """Confirm encoders are not normalized"""

    enc_weight = 5
    with nengo.Network() as model:
        norm = nengo.Ensemble(1, 1, encoders=[[enc_weight]])
        no_norm = nengo.Ensemble(
            1, 1, encoders=[[enc_weight]], normalize_encoders=False
        )

    with Simulator(model) as sim:
        pass

    assert np.allclose(sim.data[norm].encoders, 1)
    assert np.allclose(sim.data[no_norm].encoders, enc_weight)


@pytest.mark.parametrize("intercept", [1.0, 1.1])
@pytest.mark.filterwarnings("ignore:divide by zero")
def test_raises_exception_for_invalid_intercepts(Simulator, intercept):
    with nengo.Network() as model:
        nengo.Ensemble(1, 1, intercepts=[intercept])

    with pytest.raises(BuildError):
        with Simulator(model):
            pass
