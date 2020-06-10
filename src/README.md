
# Table of Contents

1.  [Source Code](#org8534190)
    1.  [Training](#orgba9da87)
        1.  [Monitored Training](#org19b7d6b)
    2.  [Model](#org36aac18)


<a id="org8534190"></a>

# Source Code

This directory contains all of the source code.
The [models](./models) directory contains the model (built in GPflow/TensorFlow) and training scripts.
The [visualization](./visualization) directory contains the `Plotter` class that can be used to plot
the model. It also contains scripts for plotting a saved model.


<a id="orgba9da87"></a>

## Training

The `Trainer` class in [models/trainer.py](./models/trainer.py) contains several training methods,

1.  A simple TensorFlow training loop,
2.  A checkpointing training loop,
3.  A monitoring tf training loop - a TensorFlow training loop with monitoring within tf.function().
    This method only monitors the model parameters and loss (elbo) and does not generate images.
4.  A monitoring training loop - this loop generates images during training. The matplotlib functions
    cannot be inside the tf.function so this training loop should be slower but provide more insights.
5.  A monitor and checkpoint loop - this loop only monitors model parameters and elbo (no images)
    but also saves checkpoints of the model.

Note that he `Trainer` class defines its own simple plotting methods.


<a id="org19b7d6b"></a>

### Monitored Training

The monitored training uses Tensorboard and is logged in [../models/logs](../models/logs).
To use Tensorboard cd to the logs directory and start Tensorboard,

    cd /path-to-this-repo/models/logs
    tensorboard --logdir . --reload_multifile=true

Tensorboard can then be found by visiting <http://localhost:6006/> in your browser.

1.  Configure Monitoring

    In the config files (e.g. [../configs/figure-3a.json](../configs/figure-3a.json)) the `fast_period` variable
    refers to how frequently the trainer should log the model parameters
    (kernel parameters, noise variances, elbo) and the `slow_period` variable
    refers to how frequently the trainer should generate images of the model (in number of iterations).


<a id="org36aac18"></a>

## Model

The [models/experts.py](./models/experts.py) file contains the base experts and two instantiations,

1.  `ExpertsSeparate` - this class creates separate inducing points for each expert.
2.  `ExpertsShared` - this class creates one set of inducing points shared by all experts.

The [models/gating<sub>network.py</sub>](./models/gating_network.py) file contains the gating network and the [models/svmogpe.py](./models/svmogpe.py) file
contains the main mixture of two GP experts class (svmogpe - Stochastic Variational Mixture of GP Experts).