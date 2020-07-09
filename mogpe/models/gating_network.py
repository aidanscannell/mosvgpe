import gpflow as gpf
import numpy as np
import tensorflow as tf
import tensorflow_probability as tfp

from gpflow import Module
from gpflow.conditionals import conditional, sample_conditional
from gpflow.conditionals.util import sample_mvn
from gpflow.config import default_float
from gpflow.models.model import InputData, MeanAndVariance
from gpflow.models.util import inducingpoint_wrapper
from gpflow.models.model import InputData, MeanAndVariance

from mogpe.models.gp import SVGPModel


def inv_probit(x):
    jitter = 1e-3  # ensures output is strictly between 0 and 1
    return 0.5 * (1.0 + tf.math.erf(x / np.sqrt(2.0))) * (1 -
                                                          2 * jitter) + jitter


class GatingNetwork(SVGPModel):
    # TODO either remove likelihood or use Bernoulli/Softmax
    def __init__(self,
                 kernel,
                 likelihood,
                 inducing_variable,
                 mean_function,
                 num_latent_gps=1,
                 q_diag=False,
                 q_mu=None,
                 q_sqrt=None,
                 whiten=True,
                 num_data=None):
        super().__init__(kernel,
                         likelihood,
                         inducing_variable,
                         mean_function,
                         num_latent_gps=num_latent_gps,
                         q_diag=q_diag,
                         q_mu=q_mu,
                         q_sqrt=q_sqrt,
                         whiten=whiten,
                         num_data=num_data)

    def _predict_prob_a_0_given_h(self, h_mean, h_var):
        return 1 - inv_probit(h_mean / (tf.sqrt(1 + h_var)))

    def predict_prob_a_0(self,
                         Xnew: InputData,
                         num_inducing_samples: int = None):
        h_mean, h_var = self.predict_f(Xnew,
                                       num_inducing_samples,
                                       full_cov=False)
        return self._predict_prob_a_0_given_h(h_mean, h_var)

    def predict_mixing_probs(self,
                             Xnew: InputData,
                             num_inducing_samples: int = None):
        """Compute mixing probabilities.

        Returns a tensor with dims
        [num_experts, num_inducing_samples, num_data, output_dim]
        if num_inducing_samples=None otherwise a tensor with dims
        [num_experts, num_data, output_dim]

        .. math::
            \\mathbf{u}_h \sim \mathcal{N}(q\_mu, q\_sqrt \cdot q\_sqrt^T) \\\\
            \\Pr(\\alpha=k | \\mathbf{Xnew}, \\mathbf{u}_h)

        :param Xnew: test input(s) [num_data, input_dim]
        :param num_inducing_samples: how many samples to draw from inducing points
        """
        prob_a_0 = self.predict_prob_a_0(Xnew, num_inducing_samples)
        prob_a_1 = 1 - prob_a_0
        # mixing_probs = tf.stack([prob_a_1, prob_a_0])
        mixing_probs = tf.stack([prob_a_0, prob_a_1])
        # mixing_probs = tf.expand_dims(mixing_probs, -1)
        # move mixture dimension to last dimension
        trailing_dims = tf.range(1, tf.rank(mixing_probs))
        transpose_shape = tf.concat([trailing_dims, [0]], 0)
        mixing_probs = tf.transpose(mixing_probs, transpose_shape)
        # mixing_probs = tf.transpose(mixing_probs, [*trailing_dims, 0])
        return mixing_probs


def init_fake_gating_network(X, Y):
    from mogpe.models.utils.model import init_inducing_variables
    output_dim = Y.shape[1]
    input_dim = X.shape[1]

    num_inducing = 7
    inducing_variable = init_inducing_variables(X, num_inducing)

    inducing_variable = gpf.inducing_variables.SharedIndependentInducingVariables(
        gpf.inducing_variables.InducingPoints(inducing_variable))

    noise_var = 0.1
    lengthscale = 1.
    mean_function = gpf.mean_functions.Zero()
    likelihood = None

    q_mu = np.zeros(
        (num_inducing, output_dim)) + np.random.randn(num_inducing, 1) * 2
    q_sqrt = np.array([
        10 * np.eye(num_inducing, dtype=default_float())
        for _ in range(output_dim)
    ])

    kern_list = []
    for _ in range(output_dim):
        # Create multioutput kernel from kernel list
        lengthscale = tf.convert_to_tensor([lengthscale] * input_dim,
                                           dtype=default_float())
        kern_list.append(gpf.kernels.RBF(lengthscales=lengthscale))
    kernel = gpf.kernels.SeparateIndependent(kern_list)

    return GatingNetwork(kernel,
                         likelihood,
                         inducing_variable,
                         mean_function,
                         q_mu=q_mu,
                         q_sqrt=q_sqrt)


if __name__ == "__main__":
    # Load data set
    from mogpe.models.utils.data import load_mixture_dataset
    data_file = '../../data/processed/artificial-data-used-in-paper.npz'
    data, F, prob_a_0 = load_mixture_dataset(filename=data_file,
                                             standardise=False)
    X, Y = data

    gating_network = init_fake_gating_network(X, Y)
    # mixing_probs = gating_network.predict_mixing_probs(X, 10)
    mixing_probs = gating_network.predict_mixing_probs(X)
    print(mixing_probs.shape)
    # print(mixing_probs[0].shape)