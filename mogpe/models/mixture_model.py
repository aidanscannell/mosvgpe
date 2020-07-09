from abc import ABC, abstractmethod
from typing import Optional, Tuple

import gpflow as gpf
import tensorflow as tf
import tensorflow_probability as tfp
from gpflow.models import BayesianModel, ExternalDataTrainingLossMixin
from gpflow.models.training_mixins import InputData, RegressionData
from gpflow import default_float

tfd = tfp.distributions


class MixtureModel(BayesianModel, ABC):
    @abstractmethod
    def predict_mixing_probs(self, Xnew, kwargs={}):
        raise NotImplementedError

    @abstractmethod
    def predict_component_dists(self, Xnew, kwargs={}):
        raise NotImplementedError

    def predict_y(self, Xnew: InputData, kwargs={}) -> tf.Tensor:
        mixing_probs = self.predict_mixing_probs(Xnew, kwargs)
        dists = self.predict_component_dists(Xnew, kwargs)
        return tfd.MixtureSameFamily(
            mixture_distribution=tfd.Categorical(probs=mixing_probs),
            components_distribution=dists)

    def predict_y_samples(self,
                          Xnew: InputData,
                          num_samples: int = 1,
                          kwargs={}) -> tf.Tensor:
        return self.predict_y(Xnew, kwargs).sample(num_samples)


class MixtureOfExperts(MixtureModel, ABC):
    def __init__(self, gating_network, experts):
        self.gating_network = gating_network
        self.experts = experts

    def predict_mixing_probs(self, Xnew, kwargs):
        return self.gating_network.predict_mixing_probs(Xnew, **kwargs)

    def predict_component_dists(self, Xnew: InputData, kwargs) -> tf.Tensor:
        dists = self.experts.predict_dists(Xnew, kwargs)
        return dists
        # return self.experts.predict_dists(Xnew, kwargs)


class GPMixtureOfExperts(MixtureOfExperts, ExternalDataTrainingLossMixin):
    def __init__(self,
                 gating_network,
                 experts,
                 num_inducing_samples=1,
                 num_data=None):
        super().__init__(gating_network, experts)
        self.num_inducing_samples = num_inducing_samples
        self.num_data = num_data

    # @tf.function
    def maximum_log_likelihood_objective(
            self, data: Tuple[tf.Tensor, tf.Tensor]) -> tf.Tensor:
        """Objective for maximum likelihood estimation.

        Lower bound to the log-marginal likelihood (ELBO).
        """
        with tf.name_scope('ELBO') as scope:
            X, Y = data

            kl_gating = self.gating_network.prior_kl()
            kls_experts = self.experts.prior_kls
            kl_experts = tf.reduce_sum(kls_experts)

            with tf.name_scope('predict_mixing_probs') as scope:
                mixing_probs = self.predict_mixing_probs(
                    X, {'num_inducing_samples': self.num_inducing_samples})
            # tf.print(mixing_probs)
            # print(mixing_probs.shape)

            # dists = self.predict_component_dists(
            #     X, {'num_inducing_samples': self.num_inducing_samples})
            # # tf.print(dists)
            # Y = tf.reshape(Y, tf.concat([tf.shape(Y), [1]], 0))
            # # expected_experts = dists.log_prob(Y)
            # expected_experts = dists.prob(Y)
            with tf.name_scope('predict_experts_prob') as scope:
                # expected_experts = self.experts.predict_prob_y(data)
                expected_experts = self.experts.predict_prob_y(
                    data, {'num_inducing_samples': self.num_inducing_samples})
                expected_experts = tf.expand_dims(expected_experts, -1)
                print('new')
                print(expected_experts.shape)

            print('expected experts')
            print(expected_experts.shape)
            print(mixing_probs.shape)
            shape_constraints = [
                (expected_experts, [
                    "num_inducing_samples", "num_data", "num_experts",
                    "output_dim"
                ]),
                (mixing_probs, [
                    "num_inducing_samples", "num_data", "output_dim",
                    "num_experts"
                ]),
            ]
            tf.debugging.assert_shapes(
                shape_constraints,
                message="Gating network and experts dimensions do not match")
            with tf.name_scope('marginalise_indicator_variable') as scope:
                weighted_sum_over_indicator = tf.matmul(
                    mixing_probs, expected_experts)
            print(weighted_sum_over_indicator.shape)

            # tf.print(weighted_sum_over_indicator)
            # log = tf.math.log(weighted_sum_over_indicator)
            # tf.print(log)
            # TODO divide by num inducing point samples
            var_exp = 1 / self.num_inducing_samples * tf.reduce_sum(
                tf.math.log(weighted_sum_over_indicator), axis=0)
            # tf.print(var_exp)
            print('var_exp')
            print(var_exp.shape)
            # TODO is output dimension being dealt with correctly here?
            var_exp = tf.linalg.diag_part(var_exp)
            print(var_exp.shape)
            print(tf.reduce_sum(var_exp).shape)

            if self.num_data is not None:
                num_data = tf.cast(self.num_data, default_float())
                minibatch_size = tf.cast(tf.shape(X)[0], default_float())
                scale = num_data / minibatch_size
            else:
                scale = tf.cast(1.0, default_float())

            # return tf.reduce_sum(var_exp) * scale
            return tf.reduce_sum(var_exp) * scale - kl_gating - kl_experts
            # return tf.reduce_sum(mixing_probs) - kl_gating - kl_experts
            # return tf.reduce_sum(expected_experts) - kl_gating - kl_experts

    def elbo(self, data: RegressionData) -> tf.Tensor:
        """
        This returns the evidence lower bound (ELBO) of the log marginal likelihood.
        """
        return self.maximum_log_likelihood_objective(data)


def init_fake_mixture(X, Y, num_experts=2, num_inducing_samples=1):
    from mogpe.models.experts import init_fake_experts
    from mogpe.models.gating_network import init_fake_gating_network
    experts = init_fake_experts(X, Y, num_experts=2)
    gating_network = init_fake_gating_network(X, Y)
    return GPMixtureOfExperts(gating_network,
                              experts,
                              num_inducing_samples=num_inducing_samples)


if __name__ == "__main__":
    from mogpe.models.utils.data import load_mixture_dataset

    # Load data set
    data_file = '../../data/processed/artificial-data-used-in-paper.npz'
    data, F, prob_a_0 = load_mixture_dataset(filename=data_file,
                                             standardise=False)
    X, Y = data

    gp_mixture_model = init_fake_mixture(X,
                                         Y,
                                         num_experts=2,
                                         num_inducing_samples=4)

    # mixture_dist = gp_mixture_model.predict_y(X, {})
    # print(mixture_dist)
    # print(mixture_dist.mixture_distribution.prob(1).shape)
    # print(mixture_dist.components_distribution)

    # import matplotlib.pyplot as plt
    # plt.plot(X, mixture_dist.prob(X))
    # plt.show()

    loss = gp_mixture_model.maximum_log_likelihood_objective(data)
    print(loss.shape)