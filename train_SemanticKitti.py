#
#
#      0=================================0
#      |    Kernel Point Convolutions    |
#      0=================================0
#
#
# ----------------------------------------------------------------------------------------------------------------------
#
#      Callable script to start a training on SemanticKitti dataset
#
# ----------------------------------------------------------------------------------------------------------------------
#
#      Hugues THOMAS - 06/03/2020
#


# ----------------------------------------------------------------------------------------------------------------------
#
#           Imports and global variables
#       \**********************************/
#

# Common libs
import signal
import os
import numpy as np
import sys
import torch

# Dataset
from datasets.SemanticKitti import *
from torch.utils.data import DataLoader

from utils.config import Config
from utils.trainer import ModelTrainer
from models.architectures import KPFCNN


# ----------------------------------------------------------------------------------------------------------------------
#
#           Config Class
#       \******************/
#

class SemanticKittiConfig(Config):
    """
    Override the parameters you want to modify for this dataset
    """

    ####################
    # Dataset parameters
    ####################

    # Dataset name
    dataset = 'SemanticKitti'

    # Number of classes in the dataset (This value is overwritten by dataset class when Initializating dataset).
    num_classes = None

    # Type of task performed on this dataset (also overwritten)
    dataset_task = ''

    # Number of CPU threads for the input pipeline
    input_threads = 20

    #########################
    # Architecture definition
    #########################

    # Define layers
    architecture = ['simple',
                    'resnetb',
                    'resnetb_strided',
                    'resnetb',
                    'resnetb',
                    'resnetb_strided',
                    'resnetb',
                    'resnetb',
                    'resnetb',
                    'resnetb',
                    'resnetb_strided',
                    'resnetb',
                    'resnetb',
                    'resnetb',
                    'resnetb_strided',
                    'resnetb',
                    'resnetb',
                    'nearest_upsample',
                    'unary',
                    'nearest_upsample',
                    'unary',
                    'nearest_upsample',
                    'unary',
                    'nearest_upsample',
                    'unary']

    ###################
    # KPConv parameters
    ###################

    # Radius of the input sphere
    in_radius = 10.0
    val_radius = 51.0
    n_frames = 1
    max_in_points = 10000
    max_val_points = 50000

    # Number of batch
    batch_num = 6
    val_batch_num = 1

    # Number of kernel points
    num_kernel_points = 15

    # Size of the first subsampling grid in meter
    first_subsampling_dl = 0.08

    # Radius of convolution in "number grid cell". (2.5 is the standard value)
    conv_radius = 2.5

    # Radius of deformable convolution in "number grid cell". Larger so that deformed kernel can spread out
    deform_radius = 6.0

    # Radius of the area of influence of each kernel point in "number grid cell". (1.0 is the standard value)
    KP_extent = 1.5

    # Behavior of convolutions in ('constant', 'linear', 'gaussian')
    KP_influence = 'linear'

    # Aggregation function of KPConv in ('closest', 'sum')
    aggregation_mode = 'sum'

    # Choice of input features
    first_features_dim = 128
    in_features_dim = 5

    # Can the network learn modulations
    modulated = False

    # Batch normalization parameters
    use_batch_norm = True
    batch_norm_momentum = 0.02

    # Offset loss
    # 'permissive' only constrains offsets inside the deform radius (NOT implemented yet)
    # 'fitting' helps deformed kernels to adapt to the geometry by penalizing distance to input points
    offsets_loss = 'fitting'
    offsets_decay = 0.01

    #####################
    # Training parameters
    #####################

    # Maximal number of epochs
    max_epoch = 500

    # Learning rate management
    learning_rate = 1e-2
    momentum = 0.98
    lr_decays = {i: 0.1 ** (1 / 100) for i in range(1, max_epoch)}
    grad_clip_norm = 100.0

    # Number of steps per epochs
    epoch_steps = 500

    # Number of validation examples per epoch
    validation_size = 50

    # Number of epoch between each checkpoint
    checkpoint_gap = 50

    # Augmentations
    augment_scale_anisotropic = True
    augment_symmetries = [True, False, False]
    augment_rotation = 'vertical'
    augment_scale_min = 0.8
    augment_scale_max = 1.2
    augment_noise = 0.001
    augment_color = 0.8

    # Choose weights for class (used in segmentation loss). Empty list for no weights
    class_w = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]

    # Do we nee to save convergence
    saving = True
    saving_path = None


# ----------------------------------------------------------------------------------------------------------------------
#
#           Main Call
#       \***************/
#

if __name__ == '__main__':

    ############################
    # Initialize the environment
    ############################

    # Set which gpu is going to be used
    GPU_ID = '2'

    # Set GPU visible device
    os.environ['CUDA_VISIBLE_DEVICES'] = GPU_ID

    ###############
    # Previous chkp
    ###############

    # Choose here if you want to start training from a previous snapshot (None for new training)
    # previous_training_path = 'Log_2020-03-19_19-53-27'
    previous_training_path = ''

    # Choose index of checkpoint to start from. If None, uses the latest chkp
    chkp_idx = None
    if previous_training_path:

        # Find all snapshot in the chosen training folder
        chkp_path = os.path.join('results', previous_training_path, 'checkpoints')
        chkps = [f for f in os.listdir(chkp_path) if f[:4] == 'chkp']

        # Find which snapshot to restore
        if chkp_idx is None:
            chosen_chkp = 'current_chkp.tar'
        else:
            chosen_chkp = np.sort(chkps)[chkp_idx]
        chosen_chkp = os.path.join('results', previous_training_path, 'checkpoints', chosen_chkp)

    else:
        chosen_chkp = None

    ##############
    # Prepare Data
    ##############

    print()
    print('Data Preparation')
    print('****************')

    # Initialize configuration class
    config = SemanticKittiConfig()
    if previous_training_path:
        config.load(os.path.join('results', previous_training_path))
        config.saving_path = None

    # Get path from argument if given
    if len(sys.argv) > 1:
        config.saving_path = sys.argv[1]

    # Initialize datasets
    training_dataset = SemanticKittiDataset(config, set='training',
                                            balance_classes=True)
    test_dataset = SemanticKittiDataset(config, set='validation',
                                        balance_classes=False)

    # Initialize samplers
    training_sampler = SemanticKittiSampler(training_dataset)
    test_sampler = SemanticKittiSampler(test_dataset)

    # Initialize the dataloader
    training_loader = DataLoader(training_dataset,
                                 batch_size=1,
                                 sampler=training_sampler,
                                 collate_fn=SemanticKittiCollate,
                                 num_workers=config.input_threads,
                                 pin_memory=True)
    test_loader = DataLoader(test_dataset,
                             batch_size=1,
                             sampler=test_sampler,
                             collate_fn=SemanticKittiCollate,
                             num_workers=config.input_threads,
                             pin_memory=True)

    # Calibrate max_in_point value
    training_sampler.calib_max_in(config, training_loader, verbose=False)
    test_sampler.calib_max_in(config, test_loader, verbose=False)

    # Calibrate samplers
    training_sampler.calibration(training_loader, verbose=True)
    test_sampler.calibration(test_loader, verbose=True)

    # debug_timing(training_dataset, training_loader)
    # debug_timing(test_dataset, test_loader)
    debug_class_w(training_dataset, training_loader)

    print('\nModel Preparation')
    print('*****************')

    # Define network model
    t1 = time.time()
    net = KPFCNN(config, training_dataset.label_values, training_dataset.ignored_labels)

    debug = False
    if debug:
        print('\n*************************************\n')
        print(net)
        print('\n*************************************\n')
        for param in net.parameters():
            if param.requires_grad:
                print(param.shape)
        print('\n*************************************\n')
        print("Model size %i" % sum(param.numel() for param in net.parameters() if param.requires_grad))
        print('\n*************************************\n')

    # Define a trainer class
    trainer = ModelTrainer(net, config, chkp_path=chosen_chkp)
    print('Done in {:.1f}s\n'.format(time.time() - t1))

    print('\nStart training')
    print('**************')

    # Training
    trainer.train(net, training_loader, test_loader, config)

    print('Forcing exit now')
    os.kill(os.getpid(), signal.SIGINT)

    # TODO: Create a function debug_class_weights that shows class distribution in input sphere. Use that as
    #  indication for the class weights during training