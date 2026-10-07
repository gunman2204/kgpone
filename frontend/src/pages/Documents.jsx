import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Loader2, UploadCloud, FileText, CheckCircle2, AlertCircle, Filter, Trash2, Eye, Download } from "lucide-react";
import api from '../lib/api';
import { useAcademic } from '../context/AcademicContext';

const Documents = () => {
  const { departments, courses: allCourses } = useAcademic();
  const [documents, setDocuments] = useState([]);
  const [filteredCourses, setFilteredCourses] = useState([]);
  const [offerings, setOfferings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isViewDialogOpen, setIsViewDialogOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState(null);
  
  // Cascading Selection State (Global for the page)
  const [selectedDeptId, setSelectedDeptId] = useState(() => localStorage.getItem('kgpone_docs_dept_id') || '');
  const [selectedCourseId, setSelectedCourseId] = useState(() => localStorage.getItem('kgpone_docs_course_id') || '');
  const [selectedOfferingId, setSelectedOfferingId] = useState(() => localStorage.getItem('kgpone_docs_offering_id') || '');

  // Persist selections to localStorage
  useEffect(() => {
    localStorage.setItem('kgpone_docs_dept_id', selectedDeptId);
  }, [selectedDeptId]);

  useEffect(() => {
    localStorage.setItem('kgpone_docs_course_id', selectedCourseId);
  }, [selectedCourseId]);

  useEffect(() => {
    localStorage.setItem('kgpone_docs_offering_id', selectedOfferingId);
  }, [selectedOfferingId]);
  
  const [formData, setFormData] = useState({ 
    title: '', 
    description: '', 
    parsing_instructions: '',
    doc_type: 'NOTES',
    file: null
  });
  
  const [submitting, setSubmitting] = useState(false);
  const { toast } = useToast();

  // Filter courses when department changes
  useEffect(() => {
    if (selectedDeptId) {
      setFilteredCourses(allCourses.filter(c => String(c.department_id) === String(selectedDeptId)));
    } else {
      setFilteredCourses([]);
    }
  }, [selectedDeptId, allCourses]);

  // Fetch offerings when course changes
  useEffect(() => {
    if (selectedCourseId) {
      api.get(`/api/v1/academic/${selectedCourseId}/offerings`)
        .then(res => setOfferings(res.data.data || []))
        .catch(err => console.error("Failed to fetch offerings", err));
    } else {
      setOfferings([]);
    }
  }, [selectedCourseId]);

  useEffect(() => {
    let timeoutId;
    let isMounted = true;

    const poll = async () => {
      if (!selectedOfferingId || !isMounted) return;
      
      try {
        const res = await api.get(`/api/v1/documents/offering/${selectedOfferingId}`);
        if (!isMounted) return;
        
        const docs = res.data.data || [];
        setDocuments(docs);
        
        const needsPolling = docs.some(doc => 
          !doc.status || doc.status.toUpperCase() === 'PROCESSING' || doc.status.toUpperCase() === 'PENDING'
        );
        
        if (needsPolling) {
          timeoutId = setTimeout(poll, 3000);
        }
      } catch (err) {
        console.error("Failed to load documents", err);
        if (isMounted) setDocuments([]);
      }
    };

    if (selectedOfferingId) {
      setLoading(true);
      poll().finally(() => {
        if (isMounted) setLoading(false);
      });
    } else {
      setDocuments([]);
    }

    return () => {
      isMounted = false;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [selectedOfferingId]);

  const handleDelete = async (docId, e) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this document? This will remove all associated graph concepts and vector embeddings.")) return;
    
    try {
      await api.delete(`/api/v1/documents/${docId}`);
      toast({ title: "Document deleted successfully." });
      setDocuments(documents.filter(d => d.id !== docId));
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Delete failed",
        description: err.response?.data?.message || err.message,
      });
    }
  };

  const handleDownload = async (docId) => {
    try {
      const res = await api.get(`/api/v1/documents/${docId}/download`);
      if (res.data.data) {
        window.open(res.data.data, "_blank");
      }
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Download failed",
        description: err.response?.data?.message || err.message,
      });
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setFormData({ ...formData, file: e.target.files[0] });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.file) {
      toast({ variant: "destructive", title: "Please select a file" });
      return;
    }
    if (!selectedOfferingId) {
      toast({ variant: "destructive", title: "Please select a Course Offering first" });
      return;
    }
    
    setSubmitting(true);
    try {
      // 1. Get presigned URL
      const presignedRes = await api.post('/api/v1/documents/presigned-url', {
        course_offering_id: selectedOfferingId,
        filename: formData.file.name,
        content_type: formData.file.type || 'application/pdf'
      });
      
      const { upload_url, file_key } = presignedRes.data.data;

      // 2. Upload file directly to S3
      await fetch(upload_url, {
        method: 'PUT',
        body: formData.file,
        headers: {
          'Content-Type': formData.file.type || 'application/pdf'
        }
      });

      // 3. Register document in backend
      const format = formData.file.name.split('.').pop().toUpperCase();
      await api.post('/api/v1/documents/', {
        course_offering_id: selectedOfferingId,
        title: formData.title,
        description: formData.description,
        parsing_instructions: formData.parsing_instructions,
        doc_type: formData.doc_type,
        format: format,
        s3_key: file_key,
        file_size_bytes: formData.file.size,
        metadata_entries: []
      });

      toast({ title: "Document uploaded and processing started!" });
      setIsDialogOpen(false);
      setFormData({ 
        title: '', description: '', 
        parsing_instructions: '', doc_type: 'NOTES', file: null 
      });
      
      // Reload documents for current offering
      setLoading(true);
      const docsRes = await api.get(`/api/v1/documents/offering/${selectedOfferingId}`);
      setDocuments(docsRes.data.data || []);
      setLoading(false);
      
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Upload failed",
        description: err.response?.data?.message || err.message,
      });
      setSubmitting(false);
    }
  };

  const getStatusBadge = (status) => {
    switch(status?.toUpperCase()) {
      case 'COMPLETED':
        return <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700 border border-green-200"><CheckCircle2 size={12}/> Processed</span>;
      case 'FAILED':
        return <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-medium text-red-700 border border-red-200"><AlertCircle size={12}/> Failed</span>;
      default:
        return <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700 border border-amber-200"><Loader2 className="animate-spin" size={12}/> Processing</span>;
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-4xl font-serif font-bold tracking-tight text-foreground mb-2">Knowledge Ingestion</h1>
          <p className="text-muted-foreground text-lg">Upload and process documents for the global semantic graph.</p>
        </div>
        
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button 
              className="px-6 py-3 bg-accent text-accent-foreground font-medium rounded-lg hover:bg-opacity-90 transition-colors flex items-center gap-2"
              disabled={!selectedOfferingId}
              onClick={(e) => {
                if (!selectedOfferingId) {
                  e.preventDefault();
                  toast({ variant: "destructive", title: "Select a Course Offering first" });
                }
              }}
            >
              <UploadCloud size={20} /> Upload Knowledge
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto bg-card border border-border p-8 rounded-xl shadow-xl">
            <DialogHeader className="mb-6">
              <DialogTitle className="text-2xl font-serif font-bold text-foreground">Upload Document</DialogTitle>
              <p className="text-muted-foreground mt-2">Uploading to selected course offering.</p>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground">Document Title *</label>
                <input 
                  type="text"
                  placeholder="e.g. Midterm Study Guide"
                  className="w-full px-4 py-3 border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-accent"
                  value={formData.title} 
                  onChange={(e) => setFormData({...formData, title: e.target.value})} 
                  required 
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-foreground">Document Type *</label>
                  <Select value={formData.doc_type} onValueChange={(val) => setFormData({...formData, doc_type: val})}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select type..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="NOTES">Notes</SelectItem>
                      <SelectItem value="PYQ">PYQ (Past Year Question)</SelectItem>
                      <SelectItem value="SYLLABUS">Syllabus</SelectItem>
                      <SelectItem value="TEXTBOOK">Textbook</SelectItem>
                      <SelectItem value="ASSIGNMENT">Assignment</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-medium text-foreground">Description</label>
                  <input 
                    type="text"
                    placeholder="Brief description..."
                    className="w-full px-4 py-3 border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-accent"
                    value={formData.description} 
                    onChange={(e) => setFormData({...formData, description: e.target.value})} 
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground">AI Parsing Instructions</label>
                <textarea 
                  placeholder="e.g., Pay special attention to extracting chemical formulas."
                  className="w-full px-4 py-3 border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-accent h-20 resize-none"
                  value={formData.parsing_instructions} 
                  onChange={(e) => setFormData({...formData, parsing_instructions: e.target.value})} 
                />
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground">Upload File</label>
                <input 
                  type="file" 
                  className="w-full px-4 py-3 border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-accent file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:bg-accent/10 file:text-accent font-medium hover:file:bg-accent/20 cursor-pointer"
                  onChange={handleFileChange} 
                  required 
                />
              </div>

              <Button 
                type="submit" 
                className="w-full bg-accent text-accent-foreground font-medium rounded-lg hover:bg-opacity-90 flex justify-center items-center gap-2 mt-4" 
                disabled={submitting}
              >
                {submitting ? <><Loader2 className="animate-spin" size={20} /> Processing...</> : "Submit to Knowledge Graph"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Global Filter Bar */}
      <Card className="rounded-lg shadow-sm border border-border bg-card">
        <CardContent className="p-4 flex flex-col md:flex-row gap-4 items-center">
          <div className="flex items-center gap-2 text-muted-foreground font-medium mr-2">
            <Filter size={18} /> Filters
          </div>
          <div className="flex-1 w-full grid grid-cols-1 md:grid-cols-3 gap-4">
            <Select value={selectedDeptId} onValueChange={(val) => {
              setSelectedDeptId(val === 'all' ? '' : val);
              setSelectedCourseId('');
              setSelectedOfferingId('');
            }}>
              <SelectTrigger>
                <SelectValue placeholder="1. Any Department" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any Department</SelectItem>
                {departments.map(d => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}
              </SelectContent>
            </Select>

            <Select value={selectedCourseId} onValueChange={(val) => {
              setSelectedCourseId(val === 'all' ? '' : val);
              setSelectedOfferingId('');
            }} disabled={!selectedDeptId}>
              <SelectTrigger>
                <SelectValue placeholder="2. Any Course" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any Course</SelectItem>
                {filteredCourses.map(c => <SelectItem key={c.id} value={c.id}>{c.code}</SelectItem>)}
              </SelectContent>
            </Select>

            <Select value={selectedOfferingId} onValueChange={(val) => setSelectedOfferingId(val === 'all' ? '' : val)} disabled={!selectedCourseId || offerings.length === 0}>
              <SelectTrigger>
                <SelectValue placeholder={offerings.length === 0 && selectedCourseId ? "No offerings available" : "3. Any Offering"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any Offering</SelectItem>
                {offerings.map(o => <SelectItem key={o.id} value={o.id}>{o.semester} {o.year}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-lg border-border shadow-sm overflow-hidden bg-card">
        <CardHeader className="bg-muted/30 border-b border-border/50 pb-4 pt-6 px-6">
          <CardTitle className="font-serif text-xl">Processed Knowledge Base</CardTitle>
          <CardDescription>
            {selectedOfferingId 
              ? "Showing documents linked to the selected academic path."
              : "Select a department, course, and offering above to view related documents."}
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader className="bg-muted/20">
              <TableRow>
                <TableHead className="font-medium px-6 py-4">Title</TableHead>
                <TableHead className="font-medium py-4">Format</TableHead>
                <TableHead className="font-medium py-4">Status</TableHead>
                <TableHead className="font-medium py-4 text-right">Ingested Date</TableHead>
                <TableHead className="font-medium py-4 text-right px-6">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && selectedOfferingId ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-16 text-muted-foreground">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto text-accent" />
                  </TableCell>
                </TableRow>
              ) : documents.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-20">
                    <div className="flex flex-col items-center justify-center">
                      <div className="h-16 w-16 bg-muted rounded-full flex items-center justify-center mb-4">
                        <FileText className="h-8 w-8 text-muted-foreground" />
                      </div>
                      <p className="text-lg font-medium text-foreground">No Knowledge Found</p>
                      <p className="text-muted-foreground mt-1 max-w-sm text-center">
                        {selectedOfferingId ? "Upload documents to populate the semantic graph for this path." : "Select a complete academic path to view documents."}
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                documents.map((doc) => (
                  <TableRow key={doc.id} className="hover:bg-muted/30 cursor-pointer transition-colors">
                    <TableCell className="font-medium px-6 py-4">{doc.title}</TableCell>
                    <TableCell className="py-4"><span className="text-xs font-mono bg-accent/10 text-accent px-2 py-1 rounded">{doc.doc_type}</span></TableCell>
                    <TableCell className="py-4">
                      {getStatusBadge(doc.status)}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-right py-4 text-sm font-mono">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right px-6 py-4">
                      <div className="flex justify-end gap-1">
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedDoc(doc);
                            setIsViewDialogOpen(true);
                          }} 
                          className="text-muted-foreground hover:text-primary hover:bg-primary/5"
                        >
                          <Eye size={16} />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={(e) => handleDelete(doc.id, e)} className="text-muted-foreground hover:text-red-600 hover:bg-red-50">
                          <Trash2 size={16} />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <Dialog open={isViewDialogOpen} onOpenChange={setIsViewDialogOpen}>
        <DialogContent className="sm:max-w-[500px] bg-card border border-border p-6 rounded-xl shadow-xl">
          {selectedDoc && (
            <>
              <DialogHeader className="mb-4">
                <DialogTitle className="text-xl font-serif font-bold text-foreground pr-8">{selectedDoc.title}</DialogTitle>
                <div className="flex gap-2 mt-2">
                  <span className="text-xs font-mono bg-accent/10 text-accent px-2 py-1 rounded">{selectedDoc.doc_type}</span>
                  {getStatusBadge(selectedDoc.status)}
                </div>
              </DialogHeader>
              
              <div className="space-y-4 text-sm text-foreground my-6">
                <div>
                  <span className="font-semibold text-muted-foreground block mb-1">Description:</span>
                  <p>{selectedDoc.description || "No description provided."}</p>
                </div>
                <div>
                  <span className="font-semibold text-muted-foreground block mb-1">Ingested Date:</span>
                  <p>{new Date(selectedDoc.created_at).toLocaleString()}</p>
                </div>
                <div>
                  <span className="font-semibold text-muted-foreground block mb-1">File Size:</span>
                  <p>{Math.round(selectedDoc.file_size_bytes / 1024)} KB</p>
                </div>
              </div>
              
              <div className="flex justify-end gap-3 mt-6">
                <Button variant="outline" onClick={() => setIsViewDialogOpen(false)}>Close</Button>
                <Button 
                  className="bg-accent text-accent-foreground hover:bg-accent/90 gap-2"
                  onClick={() => handleDownload(selectedDoc.id)}
                >
                  <Download size={16} /> Download
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Documents;
