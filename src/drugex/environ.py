#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This module is mainly for environment (predictor) construction.

It contains machine learning (ML) training, cross validation and independent set test.
The traditional ML models are implemented by using Scikit-Learn (version >= 0.18)
"""

import os

import click
import numpy as np
import pandas as pd
import torch as T
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import GridSearchCV, KFold, StratifiedKFold
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.svm import SVC, SVR
from torch.utils.data import DataLoader, TensorDataset

from drugex import util
from drugex.model import MTFullyConnected, STFullyConnected


def DNN(X, y, X_ind, y_ind, out, is_regression=False, *, batch_size, n_epoch, lr):
    """Cross Validation and independent set test for fully connected deep neural network

    Arguments:
        X (ndarray): Feature data of training and validation set for cross-validation.
                     m X n matrix, m is the No. of samples, n is the No. of fetures
        y (ndarray): Label data of training and validation set for cross-validation.
                     m X t matrix if it is for multi-task model,
                     m is the No. of samples, n is the No. of tasks or classes;
                     m-D vector if it is only for single task model, and m is the No. of samples.
        X_ind (ndarray): Feature data of independent test set for independent test.
                         It has the similar data structure as X.
        y_ind (ndarray): Feature data of independent set for for independent test.
                         It has the similar data structure as y
        out (str): The file path for saving the result data.
        is_regression (bool, optional): define the model for regression (True) or classification (False) (Default: False)

    Returns:
         cvs (ndarray): cross-validation results. If it is single task, the shape is (m, ),
                        m is the No. of samples, it contains real label and probability value;
                        if it is multi-task, the shape is m X n, n is the No. of tasks.
         inds (ndarray): independent test results. It has similar data structure as cvs.
    """
    if 'mtqsar' in out or is_regression:
        folds = KFold(5).split(X)
        NET = MTFullyConnected
    else:
        folds = StratifiedKFold(5).split(X, y[:, 0])
        NET = STFullyConnected
    indep_set = TensorDataset(T.Tensor(X_ind), T.Tensor(y_ind))
    indep_loader = DataLoader(indep_set, batch_size=batch_size)
    cvs = np.zeros(y.shape)
    inds = np.zeros(y_ind.shape)
    for i, (trained, valided) in enumerate(folds):
        train_set = TensorDataset(T.Tensor(X[trained]), T.Tensor(y[trained]))
        train_loader = DataLoader(train_set, batch_size=batch_size)
        valid_set = TensorDataset(T.Tensor(X[valided]), T.Tensor(y[valided]))
        valid_loader = DataLoader(valid_set, batch_size=batch_size)
        net = NET(X.shape[1], y.shape[1], is_reg=is_regression)
        net.fit(train_loader, valid_loader, out='%s_%d' % (out, i), epochs=n_epoch, lr=lr)
        cvs[valided] = net.predict(valid_loader)
        inds += net.predict(indep_loader)
    cv, ind = y == y, y_ind == y_ind
    return cvs[cv], inds[ind] / 5


def RF(X, y, X_ind, y_ind, is_regression=False, n_folds=5):
    """Cross Validation and independent set test for Random Forest model

    Arguments:
        X (ndarray): Feature data of training and validation set for cross-validation.
                     m X n matrix, m is the No. of samples, n is the No. of fetures
        y (ndarray): Label data of training and validation set for cross-validation.
                     m-D vector, and m is the No. of samples.
        X_ind (ndarray): Feature data of independent test set for independent test.
                         It has the similar data structure as X.
        y_ind (ndarray): Feature data of independent set for for independent test.
                         It has the similar data structure as y
        out (str): The file path for saving the result data.
        is_regression (bool, optional): define the model for regression (True) or classification (False) (Default: False)

    Returns:
         cvs (ndarray): cross-validation results. The shape is (m, ), m is the No. of samples.
         inds (ndarray): independent test results. It has similar data structure as cvs.
        """
    if is_regression:
        folds = KFold(n_folds).split(X)
        alg = RandomForestRegressor
    else:
        folds = StratifiedKFold(n_folds).split(X, y)
        alg = RandomForestClassifier
    cvs = np.zeros(y.shape)
    inds = np.zeros(y_ind.shape)
    for i, (trained, valided) in enumerate(folds):
        model = alg(n_estimators=500, n_jobs=1)
        model.fit(X[trained], y[trained])
        if is_regression:
            cvs[valided] = model.predict(X[valided])
            inds += model.predict(X_ind)
        else:
            cvs[valided] = model.predict_proba(X[valided])[:, 1]
            inds += model.predict_proba(X_ind)[:, 1]
    return cvs, inds / 5


def SVM(X, y, X_ind, y_ind, is_reg=False):
    """Cross Validation and independent set test for Support Vector Machine (SVM)

    Arguments:
        X (ndarray): Feature data of training and validation set for cross-validation.
                     m X n matrix, m is the No. of samples, n is the No. of fetures
        y (ndarray): Label data of training and validation set for cross-validation.
                     m-D vector, and m is the No. of samples.
        X_ind (ndarray): Feature data of independent test set for independent test.
                         It has the similar data structure as X.
        y_ind (ndarray): Feature data of independent set for for independent test.
                         It has the similar data structure as y
        out (str): The file path for saving the result data.
        is_reg (bool, optional): define the model for regression (True) or classification (False) (Default: False)

    Returns:
         cvs (ndarray): cross-validation results. The shape is (m, ), m is the No. of samples.
         inds (ndarray): independent test results. It has similar data structure as cvs.
    """
    if is_reg:
        folds = KFold(5).split(X)
        model = SVR()
    else:
        folds = StratifiedKFold(5).split(X, y)
        model = SVC(probability=True)
    cvs = np.zeros(y.shape)
    inds = np.zeros(y_ind.shape)
    gs = GridSearchCV(model, {'C': 2.0 ** np.array([-5, 15]), 'gamma': 2.0 ** np.array([-15, 5])}, n_jobs=5)
    gs.fit(X, y)
    params = gs.best_params_
    print(params)
    for i, (trained, valided) in enumerate(folds):
        model = SVC(probability=True, C=params['C'], gamma=params['gamma'])
        model.fit(X[trained], y[trained])
        if is_reg:
            cvs[valided] = model.predict(X[valided])
            inds += model.predict(X_ind)
        else:
            cvs[valided] = model.predict_proba(X[valided])[:, 1]
            inds += model.predict_proba(X_ind)[:, 1]
    return cvs, inds / 5


def KNN(X, y, X_ind, y_ind, is_reg=False):
    """Cross Validation and independent set test for KNN.

    Arguments:
        X (ndarray): Feature data of training and validation set for cross-validation.
                     m X n matrix, m is the No. of samples, n is the No. of fetures
        y (ndarray): Label data of training and validation set for cross-validation.
                     m-D vector, and m is the No. of samples.
        X_ind (ndarray): Feature data of independent test set for independent test.
                         It has the similar data structure as X.
        y_ind (ndarray): Feature data of independent set for for independent test.
                         It has the similar data structure as y
        out (str): The file path for saving the result data.
        is_reg (bool, optional): define the model for regression (True) or classification (False) (Default: False)

    Returns:
         cvs (ndarray): cross-validation results. The shape is (m, ), m is the No. of samples.
         inds (ndarray): independent test results. It has similar data structure as cvs.
    """
    if is_reg:
        folds = KFold(5).split(X)
        alg = KNeighborsRegressor
    else:
        folds = StratifiedKFold(5).split(X, y)
        alg = KNeighborsClassifier
    cvs = np.zeros(y.shape)
    inds = np.zeros(y_ind.shape)
    for i, (trained, valided) in enumerate(folds):
        model = alg(n_jobs=1)
        model.fit(X[trained], y[trained])
        if is_reg:
            cvs[valided] = model.predict(X[valided])
            inds += model.predict(X_ind)
        else:
            cvs[valided] = model.predict_proba(X[valided])[:, 1]
            inds += model.predict_proba(X_ind)[:, 1]
    return cvs, inds / 5


def NB(X, y, X_ind, y_ind):
    """Cross Validation and independent set test for Naive Bayes.

    Arguments:
        X (ndarray): Feature data of training and validation set for cross-validation.
                     m X n matrix, m is the No. of samples, n is the No. of fetures
        y (ndarray): Label data of training and validation set for cross-validation.
                     m-D vector, and m is the No. of samples.
        X_ind (ndarray): Feature data of independent test set for independent test.
                         It has the similar data structure as X.
        y_ind (ndarray): Feature data of independent set for for independent test.
                         It has the similar data structure as y
        out (str): The file path for saving the result data.

    Returns:
         cvs (ndarray): cross-validation results. The shape is (m, ), m is the No. of samples.
         inds (ndarray): independent test results. It has similar data structure as cvs.
    """
    folds = StratifiedKFold(5).split(X, y)
    cvs = np.zeros(y.shape)
    inds = np.zeros(y_ind.shape)
    for i, (trained, valided) in enumerate(folds):
        model = GaussianNB()
        model.fit(X[trained], y[trained])
        cvs[valided] = model.predict_proba(X[valided])[:, 1]
        inds += model.predict_proba(X_ind)[:, 1]
    return cvs, inds / 5


PAIR = ['CMPD_CHEMBLID', 'CANONICAL_SMILES', 'PCHEMBL_VALUE', 'ACTIVITY_COMMENT']


# Model performance and saving
def _main_helper(*, path, feat, alg, is_regression, batch_size, n_epoch, lr, output):
    df = pd.read_table(path)
    df = df[PAIR].set_index(PAIR[0])
    df[PAIR[2]] = df.groupby(PAIR[0]).mean()
    # The molecules that have PChEMBL value
    numery = df[PAIR[1:-1]].drop_duplicates().dropna()
    if is_regression:
        df = numery
        y = numery[PAIR[2:3]].values
    else:
        # The molecules that do not have PChEMBL value
        # but has activity comment to show whether it is active or not.
        binary = df[df.ACTIVITY_COMMENT.str.contains('Active') == True].drop_duplicates()
        binary = binary[~binary.index.isin(numery.index)]
        # binary.loc[binary.ACTIVITY_COMMENT == 'Active', 'PCHEMBL_VALUE'] = 100.0
        binary.loc[binary.ACTIVITY_COMMENT.str.contains('Not'), 'PCHEMBL_VALUE'] = 0.0
        binary = binary[PAIR[1:3]].dropna().drop_duplicates()
        df = numery.append(binary)
        # For classification model the active ligand is defined as
        # PChBMBL value >= 6.5
        y = (df[PAIR[2:3]] >= 6.5).astype(float).values
    # ECFP6 fingerprints extraction
    X = util.Environment.ECFP_from_SMILES(df.CANONICAL_SMILES).values

    os.makedirs(output, exist_ok=True)
    out = os.path.join(output, '%s_%s_%s' % (alg, 'reg' if is_regression else 'cls', feat))

    # Model training and saving
    # model = RandomForestClassifier(n_estimators=1000, n_jobs=10)
    # model.fit(X, y[:, 0])
    # joblib.dump(model, out+'.pkg')

    # Cross validation and independent test
    data = pd.DataFrame()
    test = pd.DataFrame()
    data['CANONICAL_SMILES'], data['LABEL'] = df.CANONICAL_SMILES, y[:, 0]
    test['CANONICAL_SMILES'], test['LABEL'] = df.CANONICAL_SMILES, y[:, 0]
    if alg == 'SVM':
        cv, ind = SVM(X, y[:, 0], X, y[:, 0])
    elif alg == 'KNN':
        cv, ind = KNN(X, y[:, 0], X, y[:, 0])
    elif alg == 'NB':
        cv, ind = NB(X, y[:, 0], X, y[:, 0])
    elif alg == 'DNN':
        cv, ind = DNN(X, y, X, y, out=out, is_regression=is_regression, batch_size=batch_size, n_epoch=n_epoch, lr=lr)
    elif alg == 'RF':
        cv, ind = RF(X, y[:, 0], X, y[:, 0], is_regression=is_regression)
    else:
        raise ValueError('Invalid algorithm: {}'.format(alg))

    data['SCORE'], test['SCORE'] = cv, ind
    data.to_csv(out + '.cv.txt', index=None)
    test.to_csv(out + '.ind.txt', index=None)


@click.command()
@click.option('-p', '--path', type=click.Path(file_okay=True), default='data/CHEMBL251.txt', required=True)
@click.option('-o', '--output', type=click.Path(file_okay=False, dir_okay=True), default='output', required=True)
@click.option('--lr', type=float, default=1e-5, show_default=True)
@click.option('--batch-size', type=int, default=1024, show_default=True)
@click.option('--n-epoch', type=int, default=1000, show_default=True)
@click.option('--n-threads', type=int, default=1, show_default=True)
@click.option('--regression', is_flag=True)
@click.option('-a', '--algorithm', type=click.Choice(['SVM', 'KNN', 'RF', 'DNN', 'NB']), default='RF', show_default=True)
@click.option('--cuda', is_flag=True)
def main(path, output, lr, batch_size, n_epoch, n_threads, regression, algorithm, cuda: bool):
    T.set_num_threads(n_threads)
    if cuda:
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    _main_helper(
        path=path,
        feat='ecfp6',
        alg=algorithm,
        is_regression=regression,
        batch_size=batch_size,
        n_epoch=n_epoch,
        lr=lr,
        output=output,
    )


if __name__ == '__main__':
    main()
