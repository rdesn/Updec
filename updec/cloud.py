import warnings
import jax
import jax.numpy as jnp
from sklearn.neighbors import BallTree
from updec.utils import distance

import os
from functools import cache

class Cloud(object):        ## TODO: implemtn len, get_item, etc.
    def __init__(self, facet_types, support_size="max"):
        self.N = 0 
        self.Ni = 0
        self.Nd = 0
        self.Nr = 0
        self.Nn = 0
        self.nodes = {}
        self.outward_normals = {}
        self.node_boundary_types = {}
        self.facet_nodes = {}
        self.facet_types = facet_types
        self.support_size = support_size
        self.dim = 2                ## TODO: default problem dimension is 2
        # self.facet_names = {}
        self.facet_precedence = {k:i for i,(k,v) in enumerate(facet_types.items())}        ## Facet order of precedence usefull for corner nodes membership


    def average_spacing(self):
        spacings = []
        for i in range(self.N):
            for j in range(i, self.N):
                spacings.append(distance(self.nodes[i], self.nodes[j]))
        return jnp.mean(jnp.array(spacings))

    # @cache
    def get_sorted_nodes(self):       ## LRU cache this, or turn it into @Property
        """ Return numpy arrays """
        sorted_nodes = sorted(self.nodes.items(), key=lambda x:x[0])
        return jnp.stack(list(dict(sorted_nodes).values()), axis=-1).T

    def define_local_supports(self):
        ## finds the 'support_size' nearest neighbords of each node
        self.local_supports = {}
        # if self.support_size < 0 or self.support_size==None or self.support_size>self.N-1:
        if self.support_size == "max":
            # warnings.warn("Support size is too big. Setting it to maximum")
            self.support_size = self.N-1
        assert self.support_size > 0, "Support size must be strictly greater than 0"
        assert self.support_size < self.N, "Support size must be strictly less than the number of nodes"

        #### BALL TREE METHOD
        renumb_map = {i:k for i,k in enumerate(self.nodes.keys())}
        coords = jnp.stack(list(self.nodes.values()), axis=-1).T
        # ball_tree = KDTree(coords, leaf_size=40, metric='euclidean')
        ball_tree = BallTree(coords, leaf_size=40, metric='euclidean')
        for i in range(self.N):
            _, neighboorhs = ball_tree.query(coords[i:i+1], k=self.support_size+1)
            neighboorhs = neighboorhs[0][1:]                    ## Result is a 2d list, with the first el itself
            self.local_supports[renumb_map[i]] = [renumb_map[j] for j in neighboorhs]

    def renumber_nodes(self):
        """ Places the internal nodes at the top of the list, then the dirichlet, then neumann: good for matrix afterwards """

        i_nodes = []
        d_nodes = []
        n_nodes = []
        r_nodes = []
        for i in range(self.N):         
            if self.node_boundary_types[i] == "i":
                i_nodes.append(i)
            elif self.node_boundary_types[i] == "d":
                d_nodes.append(i)
            elif self.node_boundary_types[i] == "n":
                n_nodes.append(i)
            elif self.node_boundary_types[i] == "r":
                r_nodes.append(i)

        new_numb = {v:k for k, v in enumerate(i_nodes+d_nodes+n_nodes+r_nodes)}       ## Reads as: node v is now node k

        if hasattr(self, "global_indices_rev"):
            self.global_indices_rev = {new_numb[k]: v for k, v in self.global_indices_rev.items()}
        if hasattr(self, "global_indices"):
            for i, (k, l) in self.global_indices_rev.items():
                self.global_indices = self.global_indices.at[k, l].set(i)

        self.node_boundary_types = {new_numb[k]:v for k,v in self.node_boundary_types.items()}
        self.nodes = {new_numb[k]:v for k,v in self.nodes.items()}

        if hasattr(self, 'local_supports'):
            self.local_supports = jax.tree_util.tree_map(lambda i:new_numb[i], self.local_supports)
            self.local_supports = {new_numb[k]:v for k,v in self.local_supports.items()}

        self.facet_nodes = jax.tree_util.tree_map(lambda i:new_numb[i], self.facet_nodes)

        if hasattr(self, 'outward_normals'):
            self.outward_normals = {new_numb[k]:v for k,v in self.outward_normals.items()}

        self.renumbering_map = new_numb



    def visualize_cloud(self, ax=None, title="Cloud", xlabel=r'$x$', ylabel=r'$y$', legend_size=8, figsize=(6,5), **kwargs):
        import matplotlib.pyplot as plt
        ## TODO Color and print important stuff appropriately

        if ax is None:
            fig = plt.figure(figsize=figsize)
            ax = fig.add_subplot(1, 1, 1)

        coords = self.sorted_nodes

        Ni, Nd, Nn = self.Ni, self.Nd, self.Nn
        if Ni > 0:
            ax.scatter(x=coords[:Ni, 0], y=coords[:Ni, 1], c="w", label="internal", **kwargs)
        if Nd > 0:
            ax.scatter(x=coords[Ni:Ni+Nd, 0], y=coords[Ni:Ni+Nd, 1], c="r", label="dirichlet", **kwargs)
        if Nn > 0:
            ax.scatter(x=coords[Ni+Nd:Ni+Nd+Nn, 0], y=coords[Ni+Nd:Ni+Nd+Nn, 1], c="g", label="neumann", **kwargs)
        if Ni+Nd+Nn < self.N:
            ax.scatter(x=coords[Ni+Nd+Nn:, 0], y=coords[Ni+Nd+Nn:, 1], c="b", label="robin", **kwargs)

        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(bbox_to_anchor=(1.0, 0.5), loc='center left', prop={'size': legend_size})
        plt.tight_layout()

        return ax


    def visualize_field(self, field, projection="2d", title="Field", xlabel=r'$x$', ylabel=r'$y$', levels=50, colorbar=True, ax=None, figsize=(6,5), **kwargs):
        import matplotlib.pyplot as plt

        # sorted_nodes = sorted(self.nodes.items(), key=lambda x:x[0])
        # coords = jnp.stack(list(dict(sorted_nodes).values()), axis=-1).T
        x, y = self.sorted_nodes[:, 0], self.sorted_nodes[:, 1]

        if ax is None:
            fig = plt.figure(figsize=figsize)
            if projection == "2d":
                ax = fig.add_subplot(1, 1, 1)
            elif projection == "3d":
                ax = fig.add_subplot(1, 1, 1, projection='3d')

        if projection == "2d":
            img = ax.tricontourf(x, y, field, levels=levels, **kwargs)
            if colorbar == True:
                plt.sca(ax)
                plt.colorbar(img)

        elif projection == "3d":
            img = ax.plot_trisurf(x, y, field, **kwargs)
            # fig.colorbar(img, shrink=0.25, aspect=20)

        ax.set_title(title)
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        plt.tight_layout()

        return ax, img


    def animate_fields(self, fields, filename=None, titles="Field", xlabel=r'$x$', ylabel=r'$y$', levels=50, figsize=(6,5), cmaps="jet", cbarsplit=7, duration=5, **kwargs):
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation
        import os
        """ Animation of signals """

        ## If not array already
        signals = [jnp.stack(field, axis=0) for field in fields]
        nb_signals = len(signals)

        x, y = self.sorted_nodes[:, 0], self.sorted_nodes[:, 1]

        fig, ax = plt.subplots(nb_signals, 1, figsize=figsize, sharex=True)

        ## Setup animation and colorbars
        imgs = []
        boundaries = []
        minmaxs = []
        for i in range(nb_signals):
            minmax = jnp.min(signals[i]), jnp.max(signals[i])
            minmaxs.append(minmax)
            boundaries = jnp.linspace(minmax[0], minmax[1], cbarsplit)

            imgs.append(ax[i].tricontourf(x, y, signals[i][0], levels=levels, vmin=minmax[0], vmax=minmax[1], cmap=cmaps[i], **kwargs))

            m = plt.cm.ScalarMappable(cmap=cmaps[i])
            m.set_array(signals[i])
            m.set_clim(minmax[0], minmax[1])
            plt.colorbar(m, boundaries=boundaries, shrink=1.0, aspect=10, ax=ax[i])

            try:
                title = titles[i]
            except IndexError:
                title = "field # "+str(i+1)
            ax[i].set_title(title)

            if i == nb_signals-1:
                ax[i].set_xlabel(xlabel)
            ax[i].set_ylabel(ylabel)

        ## ANimation function
        def animate(frame):
            imgs = [ax[i].tricontourf(x, y, signals[i][frame], levels=levels, vmin=minmaxs[i][0], vmax=minmaxs[i][1], cmap=cmaps[i], extend='min', **kwargs) for i in range(nb_signals)]
            # plt.suptitle("iter = "+str(i), size="large", y=0.95)      ## TODO doesn't work well with tight layout
            return imgs

        step_count = signals[0].shape[0]
        anim = FuncAnimation(fig, animate, frames=step_count, repeat=False, interval=100)
        plt.tight_layout()

        ### Save the video
        if filename:
            fps = step_count / duration
            anim.save(filename, writer='ffmpeg', fps=fps)
            os.system("open "+filename)

        return ax






class SquareCloud(Cloud):
    def __init__(self, Nx=7, Ny=5, noise_key=None, **kwargs):
        super().__init__(**kwargs)

        self.Nx = Nx
        self.Ny = Ny
        self.N = self.Nx*self.Ny
        # self.facet_types = facet_types

        self.define_global_indices()
        self.define_node_boundary_types()
        self.define_node_coordinates(noise_key)
        self.define_local_supports()
        self.define_outward_normals()
        self.renumber_nodes()

        self.sorted_nodes = self.get_sorted_nodes()

        # self.visualise_cloud()        ## TODO Finsih this properly


    def define_global_indices(self):
        ## defines the 2d to 1d indices and vice-versa

        self.global_indices = jnp.zeros((self.Nx, self.Ny), dtype=int)
        self.global_indices_rev = {}

        count = 0
        for i in range(self.Nx):
            for j in range(self.Ny):
                self.global_indices = self.global_indices.at[i,j].set(count)
                self.global_indices_rev[count] = (i,j)
                count += 1


    def define_node_coordinates(self, noise_key):
        """ Can be used to redefine coordinates for performance study """
        x = jnp.linspace(0, 1., self.Nx)
        y = jnp.linspace(0, 1., self.Ny)
        xx, yy = jnp.meshgrid(x, y)

        # if noise_key is None:
        #     noise_key = jax.random.PRNGKey(42)
 
        if noise_key is not None:
            key = jax.random.split(noise_key, self.N)
            delta_noise = min((x[1]-x[0], y[1]-y[0])) / 2.   ## To make sure nodes don't go into each other

        self.nodes = {}

        for i in range(self.Nx):
            for j in range(self.Ny):
                global_id = int(self.global_indices[i,j])

                if (self.node_boundary_types[global_id] not in ["d", "n"]) and (noise_key is not None):
                    noise = jax.random.uniform(key[global_id], (2,), minval=-delta_noise, maxval=delta_noise)         ## Just add some noisy noise !!
                else:
                    noise = jnp.zeros((2,))

                self.nodes[global_id] = jnp.array([xx[j,i], yy[j,i]]) + noise


    def define_node_boundary_types(self):
        """ Makes the boundaries for the square domain """

        self.facet_nodes = {k:[] for k in self.facet_types.keys()}     ## List of nodes belonging to each facet
        self.node_boundary_types = {}                              ## Coding structure: internal="i", dirichlet="d", neumann="n", external="e" (not supported yet)

        for i in range(self.N):
            [k, l] = list(self.global_indices_rev[i])
            if k == 0:
                self.facet_nodes["West"].append(i)
                self.node_boundary_types[i] = self.facet_types["West"]
            elif l == self.Ny-1:
                self.facet_nodes["North"].append(i)
                self.node_boundary_types[i] = self.facet_types["North"]
            elif k == self.Nx-1:
                self.facet_nodes["East"].append(i)
                self.node_boundary_types[i] = self.facet_types["East"]
            elif l == 0:
                self.facet_nodes["South"].append(i)
                self.node_boundary_types[i] = self.facet_types["South"]
            else:
                self.node_boundary_types[i] = "i"       ## Internal node (not a boundary). But very very important!

        self.Nd = 0
        self.Nn = 0
        for f_id, f_type in self.facet_types.items():
            if f_type == "d":
                self.Nd += len(self.facet_nodes[f_id])
            if f_type == "n":
                self.Nn += len(self.facet_nodes[f_id])

        self.Ni = self.N - self.Nd - self.Nn

    def define_outward_normals(self):
        ## Makes the outward normal vectors to boundaries
        bd_nodes = [k for k,v in self.node_boundary_types.items() if v in ["n", "r"]]   ## Neumann or Robin nodes
        self.outward_normals = {}

        for i in bd_nodes:
            k, l = self.global_indices_rev[i]
            if k==0:
                n = jnp.array([-1., 0.])
            elif k==self.Nx-1:
                n = jnp.array([1., 0.])
            elif l==0:
                n = jnp.array([0., -1.])
            elif l==self.Ny-1:
                n = jnp.array([0., 1.])

            ## How to enfore zeros normals at corners nodes
            # nx, ny = 1., 1.
            # if k==0:
            #     nx, ny = -nx, 0. 
            # elif k==self.Nx-1:
            #     nx, ny = nx, 0. 
            # elif l==0:
            #     nx, ny = 0., -ny 
            # elif l==self.Ny-1:
            #     nx, ny = 0., ny

            # self.outward_normals[int(self.global_indices[k,l])] = jnp.array([nx, ny])
            self.outward_normals[int(self.global_indices[k,l])] = n










class GmshCloud(Cloud):
    """ Parses gmsh format 4.0.8, not the newer version """

    def __init__(self, filename, mesh_save_location=None, **kwargs):

        super().__init__(**kwargs)

        self.get_meshfile(filename, mesh_save_location)
        # self.facet_types = facet_types

        self.extract_nodes_and_boundary_type()
        self.define_outward_normals()
        self.define_local_supports()
        self.renumber_nodes()

        self.sorted_nodes = self.get_sorted_nodes()


    def get_meshfile(self, filename, mesh_save_location):
        _, extension = filename.rsplit('.', maxsplit=1)
        if extension == "msh":   ## Gmsh Geo file
            self.filename = filename
        elif extension == "py":  ## Gmsh Python API
            os.system("python "+filename + " " + mesh_save_location +" --nopopup")
            self.filename = mesh_save_location+"mesh.msh"


    def extract_nodes_and_boundary_type(self):
        """ Extract nodes and all boundary types """

        f = open(self.filename, "r")

        #--- Facet names ---#
        line = f.readline()
        while line.find("$PhysicalNames") < 0: line = f.readline()
        splitline = f.readline().split()

        facet_physical_names = {}
        nb_facets = int(splitline[0]) - 1
        for facet in range(nb_facets):
            splitline = f.readline().split()
            facet_physical_names[int(splitline[1])] = (splitline[2])[1:-1]    ## Removes quotes

        #--- Physical names to entities ---#
        self.facet_names = {}
        line = f.readline()
        while line.find("$Entities") < 0: line = f.readline()
        splitline = f.readline().split()
        n_vertices, n_facets = int(splitline[0]), int(splitline[1])
        for _ in range(n_vertices):
            line = f.readline()     ## Skip the vertices
        for _ in range(n_facets):
            splitline = f.readline().split()     ## Skip the vertices
            self.facet_names[int(splitline[0])] = facet_physical_names[int(splitline[-4])]

        #--- Reading mesh nodes ---#
        line = f.readline()
        while line.find("$Nodes") < 0: line = f.readline()
        splitline = f.readline().split()

        self.N = int(splitline[1])
        self.nodes = {}
        self.facet_nodes = {v:[] for v in self.facet_names.values()}
        self.node_boundary_types = {}
        corner_membership = {}

        line = f.readline()
        while line.find("$EndNodes") < 0:
            splitline = line.split()
            entity_id = int(splitline[0])
            dim = int(splitline[1])
            nb = int(splitline[-1])
            facet_nodes = []

            for i in range(nb):
                splitline = f.readline().split()
                node_id = int(splitline[0]) - 1
                x = float(splitline[1])
                y = float(splitline[2])
                z = float(splitline[3])

                self.nodes[node_id] = jnp.array([x, y])

                if dim==0: ## A corner point
                    corner_membership[node_id] = []

                elif dim==1:  ## A curve
                    self.node_boundary_types[node_id] = self.facet_types[self.facet_names[entity_id]]
                    facet_nodes.append(node_id)

                elif dim==2:  ## A surface
                    self.node_boundary_types[node_id] = "i"

            if dim==1:
                self.facet_nodes[self.facet_names[entity_id]] += facet_nodes

            line = f.readline()

        # --- Read mesh elements for corner nodes ---#
        while line.find("$Elements") < 0: line = f.readline()
        f.readline()

        line = f.readline()
        while line.find("$EndElements") < 0:
            splitline = line.split()
            entity_id = int(splitline[0])
            dim = int(splitline[1])
            nb = int(splitline[-1])

            if dim == 1:                ## Only considering elements of dim=DIM-1
                for i in range(nb):
                    splitline = [int(n_id)-1 for n_id in f.readline().split()]

                    for c_node_id in corner_membership.keys():
                        if c_node_id in splitline:
                            for neighboor in splitline:
                                if neighboor != c_node_id:
                                    corner_membership[c_node_id].append(entity_id)
                                    break

            else:
                for i in range(nb): f.readline()

            line = f.readline()

        f.close()

        ## Sort the entity ids by precedence
        for c_id, f_ids in corner_membership.items():
            f_names = [self.facet_names[f_id] for f_id in f_ids]
            sorted_f = sorted(f_names, key=lambda f_name:self.facet_precedence[f_name])
            choosen_facet = sorted_f[0]   ## The corner node belongs to this facet exclusively

            self.node_boundary_types[c_id] = self.facet_types[choosen_facet]
            self.facet_nodes[choosen_facet].append(c_id)


        self.Ni = len({k:v for k,v in self.node_boundary_types.items() if v=="i"})
        self.Nd = len({k:v for k,v in self.node_boundary_types.items() if v=="d"})
        self.Nr = len({k:v for k,v in self.node_boundary_types.items() if v=="r"})
        self.Nn = len({k:v for k,v in self.node_boundary_types.items() if v=="n"})



    def define_outward_normals(self):
        ## Use the Gmesh API        https://stackoverflow.com/a/59279502/8140182

        for i in range(self.N):
            if self.node_boundary_types[i] == "i":
                i_point = self.nodes[i]     ## An interior poitn for testing
                break

        for f_name, f_nodes in self.facet_nodes.items():

            if self.facet_types[f_name] in ["n", "r"]:      ### Only Neuman and Robin need normals !

                in_vector = i_point - self.nodes[f_nodes[0]]        ## An inward pointing vector
                assert len(f_nodes)>1, " Mesh not fine enough for normal computation "
                tangent = self.nodes[f_nodes[1]] - self.nodes[f_nodes[0]]       ## A tangent vector

                normal = jnp.array([-tangent[1], tangent[0]])
                if jnp.dot(normal, in_vector) > 0:      ## The normal is pointing inward
                    for j in f_nodes:
                        self.outward_normals[j] = -normal / jnp.linalg.norm(normal)
                else:                                   ## The normal is pointing outward
                    for j in f_nodes:
                        self.outward_normals[j] = normal / jnp.linalg.norm(normal)
