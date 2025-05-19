import { createContext, PropsWithChildren, useContext, useEffect, useState, useMemo } from "react";
import { FootprintContextStruct } from "./FootprintContextStruct.tsx";
import { getPeriodDateRange, Period } from "../utils/period.tsx";
import { Dayjs } from "dayjs";
import {
    ClusterConsumption,
    ClusterFootprint,
    useGetClustersFootprintsMutation,
    useGetCarbonConsumptionMutation,
    useGetEnergyConsumptionMutation,
    useGetFinopsCostMutation,
} from "../frugalit/slices/api.tsx";
import { ApplicationContext } from "./ApplicationContextProvider.tsx";
import { useToast } from "../components/ToastProvider.tsx";
import { extractHttpErrorMessage } from "../utils/extractHttpErrorMessage.tsx";
import { debounce } from 'lodash';

/**
 * Context to provide footprint-related data and functionality throughout the application.
 * 
 * @type {React.Context<FootprintContextStruct>}
 */
export const FootprintContext = createContext<FootprintContextStruct>(null!);

/**
 * The Footprint Context Provider provides the footprint context to the application.
 * If a current cluster is selected, it fetches the detailed footprint data for the current cluster.
 * Otherwise, it fetches the footprint data for all clusters, which triggers a dedicated REST API call.
 * 
 * @param props 
 * @returns the footprint context provider
 */
export const FootprintContextProvider = (props: PropsWithChildren<{}>) => {
    const [getClusterFootprints] = useGetClustersFootprintsMutation();
    const [getCarbonConsumption] = useGetCarbonConsumptionMutation();
    const [getEnergyConsumption] = useGetEnergyConsumptionMutation();
    const [getFinopsCost] = useGetFinopsCostMutation();
    const { showError } = useToast();

    const [period, setPeriod] = useState<Period>(Period.MONTH);
    const [currentClusterFootprints] = useState<ClusterFootprint>(undefined);
    const [selectedClusterFootprints, setSelectedClusterFootprints] = useState<ClusterFootprint[]>([]);
    const [allClusterFootprints, setAllClusterFootprints] = useState<ClusterFootprint[]>([]);
    const [currentCarbonConsumption, setCurrentCarbonConsumption] = useState<ClusterConsumption>(undefined);
    const [currentEnergyConsumption, setCurrentEnergyConsumption] = useState<ClusterConsumption>(undefined);
    const [currentCostConsumption, setCurrentCostConsumption] = useState<ClusterConsumption>(undefined);

    const global_context = useContext(ApplicationContext);

    const contextValue: FootprintContextStruct = useMemo(() => ({
        period: period,
        currentClusterFootprints: currentClusterFootprints,
        selectedClusterFootprints: selectedClusterFootprints,
        allClusterFootprints: allClusterFootprints,
        currentCarbonConsumption: currentCarbonConsumption,
        currentEnergyConsumption: currentEnergyConsumption,
        currentCostConsumption: currentCostConsumption,
        updatePeriod: setPeriod,
        updateClusterFootprints: updateClusterFootprints,
        updateSelectedClusterFootprints: setSelectedClusterFootprints,
    }), [
        period, currentClusterFootprints, selectedClusterFootprints,
        allClusterFootprints, currentCarbonConsumption, currentEnergyConsumption, currentCostConsumption
    ]);

    function updateClusterFootprints(fullname: string): void {
        const c = allClusterFootprints.find(s => s.cluster.fullname === fullname);
        
        if (selectedClusterFootprints.some(s => s === c)) {
            // Remove from selected list if already selected
            setSelectedClusterFootprints(prevState => prevState.filter(s => s.cluster !== c.cluster));
        } else {
            // Add to the selected list
            setSelectedClusterFootprints(prevState => [...prevState, c]);
        }
    }

    /**
     * Fetch cluster footprints for all clusters
     */
    const fetchClustersFootprint = debounce(() => {
        const periodDates: Dayjs[] = getPeriodDateRange(period);
        const startDate: string = periodDates[0].toISOString();
        const endDate: string = periodDates[1].toISOString();

        setCurrentCarbonConsumption(undefined);
        setCurrentCostConsumption(undefined);
        setCurrentEnergyConsumption(undefined);

        getClusterFootprints({ start: startDate, end: endDate })
            .then((response) => {
                if ("error" in response) {
                    showError({
                        summary: "Error loading clusters footprint data",
                        detail: extractHttpErrorMessage(response.error),
                    });
                } else {
                    setAllClusterFootprints(response.data as ClusterFootprint[]);
                    setSelectedClusterFootprints(response.data as ClusterFootprint[]);
                }
            });
    }, 300);

    /**
     * Fetch current cluster data (carbon, energy, cost) in a single call using Promise.all
     */
    const fetchCurrentClusterData = debounce(() => {
        if (!global_context.currentClusterOverview) return;

        const periodDates: Dayjs[] = getPeriodDateRange(period);
        const startDate: string = periodDates[0].toISOString();
        const endDate: string = periodDates[1].toISOString();

        setCurrentCarbonConsumption(undefined);
        setCurrentCostConsumption(undefined);
        setCurrentEnergyConsumption(undefined);

        Promise.all([
            getCarbonConsumption({
                start: startDate,
                end: endDate,
                cluster: global_context.currentClusterOverview.alias,
                precision: global_context.currentPrecision
            }),
            getEnergyConsumption({
                start: startDate,
                end: endDate,
                cluster: global_context.currentClusterOverview.alias,
                precision: global_context.currentPrecision
            }),
            getFinopsCost({
                start: startDate,
                end: endDate,
                cluster: global_context.currentClusterOverview.alias,
                precision: global_context.currentPrecision
            })
        ])
        .then(([carbonResponse, energyResponse, costResponse]) => {
            if (!("error" in carbonResponse)) {
                setCurrentCarbonConsumption(carbonResponse.data as ClusterConsumption);
            }
            if (!("error" in energyResponse)) {
                setCurrentEnergyConsumption(energyResponse.data as ClusterConsumption);
            }
            if (!("error" in costResponse)) {
                setCurrentCostConsumption(costResponse.data as ClusterConsumption);
            }
        })
        .catch((error) => console.error('Error fetching current cluster data:', error));
    }, 300);

    useEffect(() => {
        if (global_context.currentClusterOverview && global_context.currentPrecision && period) {
            fetchCurrentClusterData();
        }
    }, [global_context.currentClusterOverview, global_context.currentPrecision, period]);

    useEffect(() => {
        if (global_context.currentPrecision && period) {
            fetchClustersFootprint();
        }
    }, [global_context.currentPrecision, period]);

    return <FootprintContext.Provider value={contextValue}>{props.children}</FootprintContext.Provider>;
};
