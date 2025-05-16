

export interface Ship {
    frequency: GLfloat
    bandwidth: GLfloat
    protocol: string
    location: string
}
export interface ShipList {
    ships: Ship[]
}

const defaultShipList: ShipList = {
    ships: []
}
export function createShipList(props: Partial<ShipList> = {}): ShipList {
    return { ...defaultShipList, ...props };
}  