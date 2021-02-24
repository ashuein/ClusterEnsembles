# ClusterEnsembles.py
#   Author: Takehiro Sano
#   Contact: tsano430@gmail.com
#   License: MIT License


import numpy as np
import pymetis
from sklearn.metrics import pairwise_distances


def create_hypergraph(base_clusters):
    """Create the incidence matrix of base clusters' hypergraph
    
    Parameter
    ----------
    base_clusters: labels generated by base clustering algorithms
    
    Return
    -------
    H: incidence matrix of base clusters' hypergraph
    """
    H = None
    len_bcs = base_clusters.shape[1]

    for bc in base_clusters:
        unique_bc = np.unique(bc[~np.isnan(bc)])
        len_unique_bc = len(unique_bc)
        bc2id = dict(zip(unique_bc, np.arange(len_unique_bc)))
        h = np.zeros((len_bcs, len_unique_bc), dtype=int)
        for i, elem_bc in enumerate(bc):
            if not np.isnan(elem_bc):
                h[i, bc2id[elem_bc]] = 1
        if H is None:
            H = h
        else:
            H = np.hstack([H, h])
    return H


def to_pymetis_format(adj_mat):
    """Transform an adjacency matrix into the pymetis format
    
    Parameter
    ---------
    adj_mat: adjacency matrix 
    
    Returns
    -------
    xadj, adjncy, eweights: parameters for pymetis
    """
    xadj = [0]
    adjncy = []
    eweights = []

    for row in adj_mat:
        idx = np.nonzero(row)[0]
        val = row[idx]
        adjncy += list(idx)
        eweights += list(val)
        xadj.append(len(adjncy))
    
    return xadj, adjncy, eweights


def cspa(base_clusters, nclass):
    """Cluster-based Similarity Partitioning Algorithm (CSPA)
    
    Parameters
    ----------
    base_clusters: labels generated by base clustering algorithms
    nclass: number of classes 
    
    Return
    -------
    celabel: concensus clustering label obtained from CSPA
    """
    H = create_hypergraph(base_clusters)
    S = np.dot(H, H.T)

    xadj, adjncy, eweights = to_pymetis_format(S)

    membership = pymetis.part_graph(nparts=nclass, xadj=xadj, adjncy=adjncy, eweights=eweights)[1]
    celabel = np.array(membership)

    return celabel


def mcla(base_clusters, nclass):
    """Meta-CLustering Algorithm (MCLA)
    
    Parameters
    ----------
    base_clusters: labels generated by base clustering algorithms
    nclass: number of classes 
    
    Return
    -------
    celabel: concensus clustering label obtained from MCLA
    """
    H = create_hypergraph(base_clusters)
    H = H.astype(bool)

    pair_dist_jac = pairwise_distances(X=H.T, metric='jaccard', n_jobs=-1)
    S = np.ones_like(pair_dist_jac) - pair_dist_jac
    S *= 1e3
    S = S.astype(int)

    xadj, adjncy, eweights = to_pymetis_format(S)

    membership = pymetis.part_graph(nparts=nclass, xadj=xadj, adjncy=adjncy, eweights=eweights)[1]

    meta_clusters = np.zeros((base_clusters.shape[1], nclass))
    for i, v in enumerate(membership):
        meta_clusters[:, v] += H[:, i]

    celabel = np.array([np.random.choice(np.nonzero(v == np.max(v))[0]) for v in meta_clusters])

    return celabel


def hbgf(base_clusters, nclass):
    """Hybrid Bipartite Graph Formulation (HBGF) 
    
    Parameters
    ----------
    base_clusters: labels generated by base clustering algorithms
    nclass: number of classes 
    
    Return
    -------
    celabel: concensus clustering label obtained from HBGF
    """
    A = create_hypergraph(base_clusters)
    rowA, colA = A.shape
    W = np.vstack([np.hstack([np.zeros((colA, colA)), A.T]), np.hstack([A, np.zeros((rowA, rowA))])])
    xadj, adjncy, _ = to_pymetis_format(W)
    membership = pymetis.part_graph(nparts=nclass, xadj=xadj, adjncy=adjncy, eweights=None)[1]
    celabel = np.array(membership[colA:])
    return celabel


def create_connectivity_matrix(base_clusters):
    """Create the connectivity matrix
    
    Parameter
    ---------
    base_clusters: labels generated by base clustering algorithms
    
    Return
    ------
    M: connectivity matrix
    """
    n_bcs, len_bcs = base_clusters.shape
    M = np.zeros((len_bcs, len_bcs))
    m = np.zeros_like(M)

    for bc in base_clusters:
        for i, elem_bc in enumerate(bc):
            m[i] = np.where(elem_bc == bc, 1, 0)
        M += m
        
    M /= n_bcs
    return M


def orthogonal_nmf_algorithm(W, nclass, maxiter=500):
    """Algorithm for bi-orthogonal three-factor NMF problem
    
    Parameters
    ----------
    W: given matrix 
    maxiter: maximum number of iterations
    
    Return
    -------
    Q, S: factor matrices
    """
    n = W.shape[0]
    Q = np.random.rand(n, nclass).reshape(n, nclass)
    S = np.diag(np.random.rand(nclass))

    for _ in range(maxiter):
        # Update Q
        WQS = np.dot(W, np.dot(Q, S))
        Q = Q * np.sqrt(WQS / (np.dot(Q, np.dot(Q.T, WQS)) + 1e-8))
        # Update S
        QTQ = np.dot(Q.T, Q)
        S = S * np.sqrt(np.dot(Q.T, np.dot(W, Q)) / (np.dot(QTQ, np.dot(S, QTQ)) + 1e-8))
    
    return Q, S


def nmf(base_clusters, nclass):
    """NMF-based consensus clustering
    
    Parameters
    ----------
    base_clusters: labels generated by base clustering algorithms
    nclass: number of classes 
    
    Return
    -------
    celabel: concensus clustering label obtained from NMF
    """
    M = create_connectivity_matrix(base_clusters)
    Q, S = orthogonal_nmf_algorithm(M, nclass)
    celabel = np.argmax(np.dot(Q, np.sqrt(S)), axis=1)
    return celabel


def cluster_ensembles(base_clusters, nclass=None, solver='hbgf', verbose=False):
    """Generate a single consensus cluster using base clusters obtained from multiple clustering algorithms
    
    Parameters
    ----------
    base_clusters: labels generated by base clustering algorithms
    nclass: number of classes 
    
    Return
    -------
    celabel: concensus clustering label 
    """
    if nclass is None:
        nclass = -1
        for bc in base_clusters:
            len_unique_bc = len(np.unique(bc[~np.isnan(bc)]))
            nclass = max(nclass, len_unique_bc)

    if verbose:
        print('Cluster Ensembles')
        print('    - number of classes: ', nclass)
        print('    - solver: ', solver)
        print('    - length of base clustering labels: ', base_clusters.shape[1])
        print('    - number of base clusters: ', base_clusters.shape[0])

    if not (isinstance(nclass, int) and nclass > 0):
        raise ValueError('Number of class must be a positive integer; got (nclass={})'.format(nclass))

    if solver == 'cspa':
        celabel = cspa(base_clusters, nclass)
    elif solver == 'mcla':
        celabel = mcla(base_clusters, nclass)
    elif solver == 'hbgf':
        celabel = hbgf(base_clusters, nclass)
    elif solver == 'nmf':
        celabel = nmf(base_clusters, nclass)
    else:
        raise ValueError("Invalid solver parameter: got '{}' instead of one of ('cspa', 'mcla', 'hbgf', 'nmf')".format(solver))

    return celabel

