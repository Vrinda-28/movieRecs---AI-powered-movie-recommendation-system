import React, { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { useAppContext } from "../../contexts/AppContext";
import ApiService from "../../services/ApiService";
import LoadingSpinner from "../Common/LoadingSpinner";
import SettingsIcon from "../Icons/SettingsIcon";
import TrashIcon from "../Icons/TrashIcon";
import UploadCloudIcon from "../Icons/UploadCloudIcon";

const formInputBase =
  "bg-slate-800 border border-slate-700 text-slate-100 px-3 py-2 sm:px-4 sm:py-2.5 rounded-lg w-full transition-colors duration-200 text-sm placeholder-slate-500";
const formInputFocus =
  "focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30";

const AdminPage = () => {
  const { token, isAdmin, loadingUser } = useAuth();
  const { showGlobalMessage, navigateTo } = useAppContext();

  // Diagnostics & Stats
  const [health, setHealth] = useState(null);
  const [dbCounts, setDbCounts] = useState(null);
  const [modelInfo, setModelInfo] = useState(null);
  const [evalData, setEvalData] = useState(null);
  const [versions, setVersions] = useState([]);
  const [loadingDashboard, setLoadingDashboard] = useState(true);

  // Retraining & Status Tracking
  const [trainingStatus, setTrainingStatus] = useState({ status: "idle" });
  const [isTriggeringRetrain, setIsTriggeringRetrain] = useState(false);
  const pollingTimerRef = useRef(null);

  // Movie Management
  const [movieLensIdState, setMovieLensIdState] = useState("");
  const [title, setTitle] = useState("");
  const [genres, setGenres] = useState("");
  const [resourceUrl, setResourceUrl] = useState("");
  const [loadingUpload, setLoadingUpload] = useState(false);
  const [adminMovies, setAdminMovies] = useState([]);
  const [loadingMovies, setLoadingMovies] = useState(false);
  const [selectedTab, setSelectedTab] = useState("overview"); // "overview" | "evaluation" | "versions" | "catalogue"

  const fetchDashboardData = useCallback(async () => {
    if (!token) return;
    try {
      const [h, counts, mInfo, evalRes, verRes, tStatus] = await Promise.all([
        ApiService.getSystemHealth(token).catch(() => null),
        ApiService.getDatabaseCounts(token).catch(() => null),
        ApiService.getModelInfo(token).catch(() => null),
        ApiService.getLatestEvaluation(token).catch(() => null),
        ApiService.getModelVersions(token).catch(() => ({ versions: [] })),
        ApiService.getLatestTrainingStatus(token).catch(() => ({ status: "idle" })),
      ]);
      setHealth(h);
      setDbCounts(counts);
      setModelInfo(mInfo);
      setEvalData(evalRes);
      setVersions(verRes?.versions || []);
      if (tStatus) setTrainingStatus(tStatus);
    } catch (err) {
      console.error("Dashboard fetch error:", err);
    } finally {
      setLoadingDashboard(false);
    }
  }, [token]);

  const fetchAdminMovies = useCallback(async () => {
    if (!token) return;
    setLoadingMovies(true);
    try {
      const data = await ApiService.getMovies(0, 50, token, null, null);
      setAdminMovies(data || []);
    } catch (err) {
      showGlobalMessage(err.message || "Failed to fetch movies.", "error");
      setAdminMovies([]);
    } finally {
      setLoadingMovies(false);
    }
  }, [token, showGlobalMessage]);

  useEffect(() => {
    if (!loadingUser) {
      if (!isAdmin) {
        showGlobalMessage("Access Denied. Administrators only.", "error");
        navigateTo("home");
        return;
      }
      fetchDashboardData();
      fetchAdminMovies();
    }
  }, [isAdmin, loadingUser, fetchDashboardData, fetchAdminMovies, navigateTo, showGlobalMessage]);

  // Polling for training status when queued or running
  useEffect(() => {
    if (trainingStatus.status === "queued" || trainingStatus.status === "running") {
      pollingTimerRef.current = setInterval(async () => {
        if (!token) return;
        try {
          const statusRes = await ApiService.getLatestTrainingStatus(token);
          setTrainingStatus(statusRes);
          if (statusRes.status === "successful" || statusRes.status === "failed") {
            clearInterval(pollingTimerRef.current);
            fetchDashboardData();
            if (statusRes.status === "successful") {
              showGlobalMessage("Model training completed successfully!", "success");
            } else {
              showGlobalMessage(`Training failed: ${statusRes.error_text || "Unknown error"}`, "error");
            }
          }
        } catch (e) {
          console.warn("Status poll error:", e);
        }
      }, 3000);
    }
    return () => {
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
    };
  }, [trainingStatus.status, token, fetchDashboardData, showGlobalMessage]);

  const handleTriggerRetrain = async () => {
    setIsTriggeringRetrain(true);
    try {
      const res = await ApiService.triggerRetrainModel(token);
      showGlobalMessage("Model retraining initiated in background worker.", "success");
      setTrainingStatus({ status: "queued", task_id: res.task_id });
    } catch (error) {
      showGlobalMessage(error.message || "Failed to trigger retraining.", "error");
    } finally {
      setIsTriggeringRetrain(false);
    }
  };

  const handleRollback = async (versionName) => {
    if (!window.confirm(`Are you sure you want to rollback to version ${versionName}?`)) return;
    try {
      await ApiService.rollbackModelVersion(versionName, token);
      showGlobalMessage(`Live model rolled back to ${versionName}`, "success");
      fetchDashboardData();
    } catch (error) {
      showGlobalMessage(error.message || "Rollback failed.", "error");
    }
  };

  const handleUploadMovie = async (e) => {
    e.preventDefault();
    setLoadingUpload(true);
    let parsedMovieLensId = null;
    if (movieLensIdState.trim() !== "") {
      parsedMovieLensId = parseInt(movieLensIdState);
      if (isNaN(parsedMovieLensId)) {
        showGlobalMessage("MovieLens ID must be a number.", "error");
        setLoadingUpload(false);
        return;
      }
    }

    const movieData = {
      title,
      genres: genres.trim() || null,
      resource_url: resourceUrl.trim() || null,
      movie_lens_id: parsedMovieLensId,
    };

    try {
      await ApiService.createMovie(movieData, token);
      showGlobalMessage(`Movie "${title}" added to catalogue!`, "success");
      setMovieLensIdState("");
      setTitle("");
      setGenres("");
      setResourceUrl("");
      fetchAdminMovies();
      fetchDashboardData();
    } catch (error) {
      showGlobalMessage(error.message || "Failed to upload movie.", "error");
    } finally {
      setLoadingUpload(false);
    }
  };

  const handleDeleteMovie = async (movieToDelete) => {
    const movieId = typeof movieToDelete === "object" ? movieToDelete.id : movieToDelete;
    const movieTitle = typeof movieToDelete === "object" ? movieToDelete.title : `ID ${movieId}`;
    if (!window.confirm(`Delete movie "${movieTitle}"? This cannot be undone.`)) return;
    try {
      await ApiService.deleteMovie(movieId, token);
      showGlobalMessage(`Movie "${movieTitle}" deleted.`, "success");
      fetchAdminMovies();
      fetchDashboardData();
    } catch (error) {
      showGlobalMessage(error.message || "Failed to delete movie.", "error");
    }
  };

  if (loadingUser || loadingDashboard) {
    return (
      <div className="container mx-auto flex flex-col justify-center items-center min-h-[60vh] gap-3">
        <LoadingSpinner size="lg" />
        <p className="text-slate-400 text-sm font-medium">Loading Administrator Console...</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-lg bg-indigo-950/80 border border-indigo-500/40 text-indigo-400">
              <SettingsIcon className="w-5 h-5" />
            </span>
            <h1 className="text-2xl font-bold text-white tracking-tight">Recommender Control Plane</h1>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            System diagnostics, offline evaluation tracking, version lineage, and catalogue governance.
          </p>
        </div>

        {/* Retrain Action Button & Live Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs">
            <span className={`w-2 h-2 rounded-full ${
              trainingStatus.status === "running" ? "bg-amber-400 animate-pulse" :
              trainingStatus.status === "queued" ? "bg-sky-400 animate-pulse" :
              trainingStatus.status === "successful" ? "bg-emerald-400" :
              trainingStatus.status === "failed" ? "bg-rose-400" : "bg-slate-500"
            }`} />
            <span className="font-mono uppercase text-slate-300">Status: {trainingStatus.status}</span>
          </div>

          <button
            onClick={handleTriggerRetrain}
            disabled={isTriggeringRetrain || trainingStatus.status === "running" || trainingStatus.status === "queued"}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition-all shadow-md shadow-indigo-950/50 flex items-center gap-2"
          >
            {isTriggeringRetrain ? <LoadingSpinner size="sm" /> : <UploadCloudIcon className="w-4 h-4" />}
            <span>Retrain Model</span>
          </button>
        </div>
      </div>

      {/* System Health Indicators */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center gap-3">
          <span className={`w-3 h-3 rounded-full ${health?.database?.healthy ? "bg-emerald-400 shadow-emerald-500/40 shadow-sm" : "bg-rose-500"}`} />
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase">Database</div>
            <div className="text-sm font-bold text-white">{health?.database?.healthy ? "Connected" : "Disconnected"}</div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center gap-3">
          <span className={`w-3 h-3 rounded-full ${health?.redis?.healthy ? "bg-emerald-400 shadow-emerald-500/40 shadow-sm" : "bg-amber-500"}`} />
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase">Redis Broker</div>
            <div className="text-sm font-bold text-white">{health?.redis?.healthy ? "Online" : "Unreachable"}</div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center gap-3">
          <span className={`w-3 h-3 rounded-full ${health?.celery_worker?.healthy ? "bg-emerald-400 shadow-emerald-500/40 shadow-sm" : "bg-amber-500"}`} />
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase">Celery Worker</div>
            <div className="text-sm font-bold text-white">{health?.celery_worker?.healthy ? "Active" : "Standby"}</div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center gap-3">
          <span className={`w-3 h-3 rounded-full ${health?.recommender_model?.healthy ? "bg-emerald-400 shadow-emerald-500/40 shadow-sm" : "bg-rose-500"}`} />
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase">Live GRU4Rec</div>
            <div className="text-sm font-bold text-white">{health?.recommender_model?.healthy ? "Deployed" : "Missing"}</div>
          </div>
        </div>
      </div>

      {/* Database Entity Row Counts */}
      {dbCounts && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: "Users", val: dbCounts.users },
            { label: "Movies", val: dbCounts.movies },
            { label: "Ratings", val: dbCounts.ratings },
            { label: "Reviews", val: dbCounts.reviews },
            { label: "Watchlists", val: dbCounts.watchlist_entries },
            { label: "Interactions", val: dbCounts.interactions },
          ].map((item) => (
            <div key={item.label} className="p-3.5 rounded-xl bg-slate-900/50 border border-slate-800/80 text-center">
              <div className="text-xl font-mono font-bold text-indigo-300">{(item.val || 0).toLocaleString()}</div>
              <div className="text-xs font-medium text-slate-400 uppercase mt-0.5">{item.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs Navigation */}
      <div className="flex border-b border-slate-800 gap-2">
        {[
          { id: "overview", label: "Model Lineage & Line" },
          { id: "evaluation", label: "Offline Evaluation Benchmark" },
          { id: "versions", label: `Model Versions (${versions.length})` },
          { id: "catalogue", label: "Catalogue Governance" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setSelectedTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition-colors ${
              selectedTab === tab.id
                ? "border-indigo-500 text-white"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 1: Live Model Metadata & Lineage */}
      {selectedTab === "overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <span>✦</span> Live Model Hyperparameters
            </h3>
            {modelInfo?.sidecar ? (
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                  <span className="text-slate-400">Embedding Dimension:</span>
                  <div className="font-mono font-bold text-white text-sm mt-0.5">{modelInfo.sidecar.embedding_dim}</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                  <span className="text-slate-400">GRU Hidden Units:</span>
                  <div className="font-mono font-bold text-white text-sm mt-0.5">{modelInfo.sidecar.gru_units}</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                  <span className="text-slate-400">Context Window (L):</span>
                  <div className="font-mono font-bold text-white text-sm mt-0.5">{modelInfo.sidecar.window_length}</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                  <span className="text-slate-400">Batch Size:</span>
                  <div className="font-mono font-bold text-white text-sm mt-0.5">{modelInfo.sidecar.batch_size}</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                  <span className="text-slate-400">Learning Rate:</span>
                  <div className="font-mono font-bold text-white text-sm mt-0.5">{modelInfo.sidecar.learning_rate}</div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                  <span className="text-slate-400">Zero-Masking:</span>
                  <div className="font-mono font-bold text-white text-sm mt-0.5">{String(modelInfo.sidecar.mask_zero)}</div>
                </div>
              </div>
            ) : (
              <p className="text-slate-400 text-sm">No live model sidecar metadata found.</p>
            )}
          </div>

          <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <span>✦</span> Training Lineage & Convergence
            </h3>
            {modelInfo?.sidecar ? (
              <div className="space-y-3 text-xs">
                <div className="flex justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">Dataset Name:</span>
                  <span className="font-mono font-semibold text-slate-200">{modelInfo.sidecar.dataset_name}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">Interactions / Examples:</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {modelInfo.sidecar.total_interactions_count?.toLocaleString()} ratings / {modelInfo.sidecar.training_examples_count?.toLocaleString()} seqs
                  </span>
                </div>
                <div className="flex justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">Actual Epochs / Duration:</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {modelInfo.sidecar.epochs_actual} epochs ({modelInfo.sidecar.training_duration_seconds}s)
                  </span>
                </div>
                <div className="flex justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">Final Train / Val Loss:</span>
                  <span className="font-mono font-semibold text-emerald-400">
                    {modelInfo.sidecar.final_train_loss} / {modelInfo.sidecar.final_val_loss ?? "N/A"}
                  </span>
                </div>
                <div className="flex justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">Git Commit:</span>
                  <span className="font-mono text-indigo-300">{modelInfo.sidecar.git_commit_hash}</span>
                </div>
              </div>
            ) : (
              <p className="text-slate-400 text-sm">Lineage unavailable.</p>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: Latest Offline Evaluation Benchmark */}
      {selectedTab === "evaluation" && (
        <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <h3 className="text-lg font-bold text-white">Offline Empirical Benchmark</h3>
              <p className="text-slate-400 text-xs mt-0.5">
                Leave-last-out evaluation on held-out user interactions. Read directly from disk artifacts.
              </p>
            </div>
            {evalData?.status === "MEASURED" && (
              <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 border border-emerald-500/40 text-emerald-300 self-start">
                Measured ({evalData.users_evaluated} Users / {evalData.total_ratings?.toLocaleString()} Ratings)
              </span>
            )}
          </div>

          {evalData?.status === "NOT YET MEASURED" ? (
            <div className="py-12 text-center text-slate-400 font-mono text-sm">
              [ NOT YET MEASURED ]
              <p className="text-xs text-slate-500 mt-1">Run `python3 scripts/run_experiments.py` to generate evaluation artifacts.</p>
            </div>
          ) : (
            <div className="space-y-6">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 text-slate-400 font-mono uppercase border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4">Metric</th>
                      <th className="py-3 px-4 text-indigo-300">GRU4Rec (Model)</th>
                      <th className="py-3 px-4 text-amber-300">Popularity Baseline</th>
                      <th className="py-3 px-4">Relative Lift</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    <tr>
                      <td className="py-3 px-4 text-slate-300 font-sans font-semibold">Hit Rate@5</td>
                      <td className="py-3 px-4 text-white font-bold">{((evalData.gru4rec?.["hit_rate@5"] || 0) * 100).toFixed(2)}%</td>
                      <td className="py-3 px-4 text-slate-300">{((evalData.popularity?.["hit_rate@5"] || 0) * 100).toFixed(2)}%</td>
                      <td className="py-3 px-4 text-emerald-400">+{(((evalData.gru4rec?.["hit_rate@5"] || 0) / Math.max(0.001, evalData.popularity?.["hit_rate@5"] || 0) - 1) * 100).toFixed(0)}%</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-slate-300 font-sans font-semibold">Hit Rate@10 (95% CI)</td>
                      <td className="py-3 px-4 text-indigo-300 font-bold">
                        {((evalData.gru4rec?.["hit_rate@10"] || 0) * 100).toFixed(2)}%
                        {evalData.gru4rec_hit10_ci95 && ` [${(evalData.gru4rec_hit10_ci95[1]*100).toFixed(1)}%, ${(evalData.gru4rec_hit10_ci95[2]*100).toFixed(1)}%]`}
                      </td>
                      <td className="py-3 px-4 text-amber-300">
                        {((evalData.popularity?.["hit_rate@10"] || 0) * 100).toFixed(2)}%
                        {evalData.popularity_hit10_ci95 && ` [${(evalData.popularity_hit10_ci95[1]*100).toFixed(1)}%, ${(evalData.popularity_hit10_ci95[2]*100).toFixed(1)}%]`}
                      </td>
                      <td className="py-3 px-4 text-emerald-400 font-bold">
                        +{(((evalData.gru4rec?.["hit_rate@10"] || 0) / Math.max(0.001, evalData.popularity?.["hit_rate@10"] || 0) - 1) * 100).toFixed(0)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-slate-300 font-sans font-semibold">NDCG@10</td>
                      <td className="py-3 px-4 text-white font-bold">{evalData.gru4rec?.["ndcg@10"]?.toFixed(4)}</td>
                      <td className="py-3 px-4 text-slate-300">{evalData.popularity?.["ndcg@10"]?.toFixed(4)}</td>
                      <td className="py-3 px-4 text-emerald-400">+{(((evalData.gru4rec?.["ndcg@10"] || 0) / Math.max(0.001, evalData.popularity?.["ndcg@10"] || 0) - 1) * 100).toFixed(0)}%</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-slate-300 font-sans font-semibold">Catalogue Coverage</td>
                      <td className="py-3 px-4 text-indigo-300 font-bold">{((evalData.gru4rec_coverage || 0) * 100).toFixed(1)}%</td>
                      <td className="py-3 px-4 text-amber-300">{((evalData.popularity_coverage || 0) * 100).toFixed(1)}%</td>
                      <td className="py-3 px-4 text-emerald-400">{((evalData.gru4rec_coverage || 0) / Math.max(0.001, evalData.popularity_coverage || 0)).toFixed(1)}x reach</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Simple Comparison Bar Chart */}
              <div className="space-y-4 pt-4 border-t border-slate-800">
                <div className="text-xs font-semibold text-slate-300">Hit Rate @ 10 Comparison:</div>
                <div className="space-y-2">
                  <div>
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>GRU4Rec (Personalized)</span>
                      <span className="font-mono text-indigo-300 font-bold">{((evalData.gru4rec?.["hit_rate@10"] || 0) * 100).toFixed(2)}%</span>
                    </div>
                    <div className="w-full bg-slate-800 h-3 rounded-full overflow-hidden">
                      <div className="bg-indigo-500 h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(100, (evalData.gru4rec?.["hit_rate@10"] || 0) * 500)}%` }} />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>Popularity Baseline</span>
                      <span className="font-mono text-amber-300 font-bold">{((evalData.popularity?.["hit_rate@10"] || 0) * 100).toFixed(2)}%</span>
                    </div>
                    <div className="w-full bg-slate-800 h-3 rounded-full overflow-hidden">
                      <div className="bg-amber-500 h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(100, (evalData.popularity?.["hit_rate@10"] || 0) * 500)}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: Model Versioning & Rollback */}
      {selectedTab === "versions" && (
        <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4">
          <h3 className="text-base font-bold text-white">Archived Model Versions</h3>
          {versions.length === 0 ? (
            <p className="text-slate-400 text-sm">No archived versions found in `models_store/versions/`.</p>
          ) : (
            <div className="divide-y divide-slate-800">
              {versions.map((ver) => (
                <div key={ver.version_filename} className="py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-white">{ver.version_filename}</span>
                      {ver.is_active && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 border border-emerald-500/50 text-emerald-300 uppercase">
                          Active Live
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5 font-mono">
                      Created: {new Date(ver.created_at).toLocaleString()} | Size: {(ver.size_bytes / (1024*1024)).toFixed(2)} MB | Train Loss: {ver.metadata?.final_train_loss ?? "N/A"}
                    </div>
                  </div>

                  {!ver.is_active && (
                    <button
                      onClick={() => handleRollback(ver.version_filename)}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors"
                    >
                      Rollback to this
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 4: Catalogue Management */}
      {selectedTab === "catalogue" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Add Movie Form */}
          <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 lg:col-span-1">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <UploadCloudIcon className="w-5 h-5 text-indigo-400" />
              Add Movie to Catalogue
            </h3>
            <form onSubmit={handleUploadMovie} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Movie Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Inception (2010)"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className={`${formInputBase} ${formInputFocus}`}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Genres (Pipe-separated)</label>
                <input
                  type="text"
                  placeholder="e.g. Action|Sci-Fi|Thriller"
                  value={genres}
                  onChange={(e) => setGenres(e.target.value)}
                  className={`${formInputBase} ${formInputFocus}`}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Poster Image URL</label>
                <input
                  type="url"
                  placeholder="https://image.tmdb.org/..."
                  value={resourceUrl}
                  onChange={(e) => setResourceUrl(e.target.value)}
                  className={`${formInputBase} ${formInputFocus}`}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">MovieLens ID (Optional)</label>
                <input
                  type="number"
                  placeholder="e.g. 109487"
                  value={movieLensIdState}
                  onChange={(e) => setMovieLensIdState(e.target.value)}
                  className={`${formInputBase} ${formInputFocus}`}
                />
              </div>

              <button
                type="submit"
                disabled={loadingUpload}
                className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition-all shadow-md shadow-indigo-950/40"
              >
                {loadingUpload ? <LoadingSpinner size="sm" /> : "Save Movie"}
              </button>
            </form>
          </div>

          {/* Existing Movies Table */}
          <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4 lg:col-span-2">
            <h3 className="text-base font-bold text-white">Catalogue Preview (First 50)</h3>
            {loadingMovies ? (
              <div className="py-8 flex justify-center"><LoadingSpinner /></div>
            ) : (
              <div className="overflow-x-auto max-h-[500px]">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 font-mono uppercase sticky top-0">
                    <tr>
                      <th className="py-2.5 px-3">ID</th>
                      <th className="py-2.5 px-3">Title</th>
                      <th className="py-2.5 px-3">Genres</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {adminMovies.map((m) => (
                      <tr key={m.id} className="hover:bg-slate-800/40">
                        <td className="py-2 px-3 font-mono text-slate-400">{m.id}</td>
                        <td className="py-2 px-3 font-medium text-slate-100 max-w-[200px] truncate">{m.title}</td>
                        <td className="py-2 px-3 text-slate-400 max-w-[150px] truncate">{m.genres || "-"}</td>
                        <td className="py-2 px-3 text-right">
                          <button
                            onClick={() => handleDeleteMovie(m)}
                            className="p-1 text-slate-400 hover:text-rose-400 transition-colors"
                            title="Delete movie"
                          >
                            <TrashIcon className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPage;
