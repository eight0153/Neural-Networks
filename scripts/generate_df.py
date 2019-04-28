"""This script takes output generated by `grid_search.py` and generates a pandas dataframe."""

import argparse
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd


def setup(results_dir):
    """Determine the data structure.

    :param results_dir: The directory where the results are located.
    :return: An empty pandas dataframe with the columns filled in, and the expected number of samples for
    each set of data.
    """
    n_trials = 0
    df = None

    for path, subdirs, files in os.walk(results_dir):
        if not subdirs:  # i.e. leaf directory
            with open(path + '/statistics.json', 'r') as f:
                stats = json.load(f)

            metrics = set()

            for filename in files:
                if filename.endswith('.npy'):
                    filepath = '%s/%s' % (path, filename)
                    a = np.load(filepath)

                    if n_trials > 0:
                        assert a.shape[0] == n_trials, 'Inconsistent number of trials in data. Expected %d ' \
                                                       'trials, but instead got %d from the file \'%s\'' \
                                                       % (n_trials, a.shape[0], filepath)
                    else:
                        n_trials = a.shape[0]

                    metrics.add(filename[:-4])

            param_names = list(stats['params'].keys())
            data_fields = ['%s_%02d' % (metric, n) for metric in metrics for n in range(n_trials)]
            data_fields += ['n_epochs_%02d' % n for n in range(n_trials)]
            df = pd.DataFrame(columns=['run_id'] + param_names + data_fields)
            df = df.set_index('run_id')

            break

    return df, n_trials


def add_failure_stats(df):
    # Failure for a regression model is when the RMSE loss gets stuck at 0.5. This does not apply to all models and datasets
    # but applies mainly to the datasets where the output space is in the set {0, 1}^1, i.e. a single binary value.
    df_regression = df[df['clf_type'] == 'MLPRegressor']
    train_loss_cols = df.filter(regex='train_loss_\d{2}').columns.values

    # axis=1 takes the sum along the rows (axis=0 does this along the columns)
    fail_count = (np.abs(df_regression[train_loss_cols] - 0.5) < 0.01).sum(axis=1) + \
                 (df_regression[train_loss_cols].isna().sum(axis=1))
    fail_rate = fail_count / len(train_loss_cols)
    df_regression = df_regression.assign(fail_count=fail_count, fail_rate=fail_rate)

    # Failure for a classification model is when the accuracy gets stuck at 0.5. This does not apply to all models and datasets
    # but applies mainly to the datasets where the output space is in the set {0, 1}^1, i.e. a single binary value.                   
    df_classification = df[df['clf_type'] == 'MLPClassifier']
    train_scores_cols = df.filter(regex='train_scores_\d{2}').columns.values

    fail_count = (np.abs(df_classification[train_scores_cols] - 0.5) < 0.01).sum(axis=1) + \
                 (df_classification[train_scores_cols].isna().sum(axis=1))
    fail_rate = fail_count / len(train_scores_cols)
    df_classification = df_classification.assign(fail_count=fail_count, fail_rate=fail_rate)

    df = pd.concat([df_regression, df_classification])

    return df


def add_summary_stats(df):
    train_loss_cols = df.filter(regex='train_loss_\d{2}').columns.values
    train_scores_cols = df.filter(regex='train_scores_\d{2}').columns.values
    val_loss_cols = df.filter(regex='val_loss_\d{2}').columns.values
    val_scores_cols = df.filter(regex='val_scores_\d{2}').columns.values
    n_epochs_cols = df.filter(regex='n_epochs_\d{2}').columns.values

    df['mean_train_loss'] = df[train_loss_cols].mean(axis=1)
    df['mean_train_scores'] = df[train_scores_cols].mean(axis=1)
    df['mean_val_loss'] = df[val_loss_cols].mean(axis=1)
    df['mean_val_scores'] = df[val_scores_cols].mean(axis=1)
    df['mean_n_epochs'] = df[n_epochs_cols].mean(axis=1)

    df['median_train_loss'] = df[train_loss_cols].median(axis=1)
    df['median_train_scores'] = df[train_scores_cols].median(axis=1)
    df['median_val_loss'] = df[val_loss_cols].median(axis=1)
    df['median_val_scores'] = df[val_scores_cols].median(axis=1)
    df['median_n_epochs'] = df[n_epochs_cols].median(axis=1)

    df['std_train_loss'] = df[train_loss_cols].std(axis=1)
    df['std_train_scores'] = df[train_scores_cols].std(axis=1)
    df['std_val_loss'] = df[val_loss_cols].std(axis=1)
    df['std_val_scores'] = df[val_scores_cols].std(axis=1)
    df['std_n_epochs'] = df[n_epochs_cols].std(axis=1)

    return df


def main(results_dir, output_file):
    df, n_trials = setup(results_dir)
    run_number = 0

    start = datetime.now()

    for path, subdirs, files in os.walk(results_dir):
        if not subdirs:  # i.e. leaf directory
            with open(path + '/statistics.json', 'r') as f:
                stats = json.load(f)

            run_number += 1
            print('\rProcessing run %d (%s) - Elapsed Time: %s' % (run_number, stats['run_id'], datetime.now() - start),
                  end='')

            series = pd.Series(stats['params'], index=df.columns)

            for filename in files:
                if filename.endswith('.npy'):
                    metric = filename[:-4]
                    filepath = '%s/%s' % (path, filename)
                    a = np.load(filepath)

                    assert a.shape[0] == n_trials, 'Expected %d samples, but the data from the file \'%s\' ' \
                                                   'implies only %d samples.' % (n_trials, filepath, a.shape[0])

                    a = a.T
                    a = pd.DataFrame(a)
                    a = a.replace([np.inf, -np.inf], np.nan)

                    # Find the last valid data point (highest epoch number).
                    idx = a.apply(pd.Series.last_valid_index)

                    for col, row in enumerate(idx):
                        # row can be None (`a` was all NaNs or infs) or
                        # nan (this row in `a` was all NaNs or infs).
                        if row and not np.isnan(row):
                            the_column = '%s_%02d' % (metric, col)
                            # `row` is sometimes a float, indexing requires ints
                            series[the_column] = a.iloc[int(row), col]
                            # Record how many epochs this trial was trained for
                            series['n_epochs_%02d' % col] = row

            df.loc[stats['run_id']] = series

    print()

    df = add_failure_stats(df)
    df = add_summary_stats(df)

    df.to_csv(output_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates a compressed view of the results.\n'
                                                 'A pandas dataframe is generated which for each run (or grid search '
                                                 'configuration) the hyperparameter settings, and the last valid value '
                                                 'for the training loss, training scores, validation loss, and '
                                                 'validation scores.')
    parser.add_argument('-r', '--results-dir', type=str, default='../results', help='Where the results are located.')
    parser.add_argument('-o', '--output', type=str, default='results_summary.csv',
                        help='The file to save the generated dataframe to.')

    args = parser.parse_args()

    main(args.results_dir, args.output)
