import networkx as nx
import matplotlib.pyplot as plt

class Ligne():
    
    def __init__(self):
        self.G = nx.Graph()

        self.G.add_node(1)
        self.G.add_nodes_from([2, 3, 4])
    
    def draw(self):
        nx.draw(self.G, with_labels=True)
        plt.show()
        plt.savefig("graphe.png")
